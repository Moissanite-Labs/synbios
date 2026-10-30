import tempfile
import unittest
from pathlib import Path

from synbios.store import DomainError, Store
from synbios.sym2p import EncodeContext, PacketRejected, apply_packet, encode_command, packet_line, parse_packet_line


class Sym2pPacketBindingTests(unittest.TestCase):
    """A packet is applied only if it says exactly what it does, once."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(str(Path(directory.name) / "forge.sqlite"))
        self.addCleanup(self.store.close)
        self.owner = self.store.bootstrap()["token"]
        self.actor = self.store.snapshot(self.owner)["actor"]
        self.project = self.store.command(self.owner, "project.create", {"name": "P", "description": "", "repository": ""})
        self.task = self.store.command(
            self.owner, "task.create", {"project_id": self.project["id"], "title": "T", "criteria": ["c"], "scope": ["s"]}
        )
        self.decoy = self.store.command(
            self.owner, "task.create", {"project_id": self.project["id"], "title": "D", "criteria": ["c"], "scope": ["s"]}
        )

    def ctx(self, packet_id="c001", step=1, project_hex=None):
        return EncodeContext(
            packet_id=packet_id,
            project_hex=project_hex or self.project["id"],
            task_hex=self.task["id"],
            sender_hex=self.actor["id"],
            sender_human=True,
            step=step,
        )

    def cancel_line(self, **kwargs):
        return encode_command("task.transition", {"task_id": self.task["id"], "status": "cancelled"}, self.ctx(**kwargs))

    def project_line(self, name="Lab", project_hex="0f" * 16, **kwargs):
        # The store assigns the new id; prj is a fresh placeholder by default.
        payload = {"name": name, "description": "", "repository": ""}
        return encode_command("project.create", payload, self.ctx(project_hex=project_hex, **kwargs))

    def events(self):
        return self.store.snapshot(self.owner)["events"]

    def assert_rejected(self, line, error=PacketRejected):
        count = len(self.events())
        with self.assertRaises(error):
            apply_packet(self.store, self.owner, line)
        self.assertEqual(len(self.events()), count)

    def tampered(self, line, edit):
        packet = parse_packet_line(line)
        edit(packet)
        return packet_line(packet)

    def test_honest_packet_applies(self):
        apply_packet(self.store, self.owner, self.cancel_line())
        self.assertEqual(self.events()[-1]["payload"]["sym2p_packet_key"], f"h{self.actor['id'][:31]}/c001")

    def test_header_must_match_decoded_command(self):
        line = self.cancel_line()
        edits = {
            "recipient": lambda p: p.update(t="qa"),
            "speech act": lambda p: p.update(a="accept"),
            "epistemic status": lambda p: p.update(st="verified"),
            "subject": lambda p: p.update(s="t" + self.decoy["id"][:31]),
            "request": lambda p: p.update(rq="decide"),
            "project": lambda p: p.update(prj="p" + "0" * 31),
            "extra tail": lambda p: p["ext"]["synbios"]["tails"].update(h="0"),
        }
        for name, edit in edits.items():
            with self.subTest(name):
                self.assert_rejected(self.tampered(line, edit))
        apply_packet(self.store, self.owner, line)

    def test_repeated_or_unknown_field_lines_are_rejected(self):
        line = self.project_line(name="Real")
        edits = {
            "earlier conflicting value": lambda p: p["cond"].insert(0, "synbios/name=Decoy"),
            "later conflicting value": lambda p: p["cond"].append("synbios/name=Decoy"),
            "unknown field": lambda p: p["cond"].append("synbios/owner=someone"),
        }
        for name, edit in edits.items():
            with self.subTest(name):
                self.assert_rejected(self.tampered(line, edit))
        status = self.tampered(self.cancel_line(), lambda p: p["ops"].insert(0, {"op": "set", "path": "/status", "from": "-", "to": "open"}))
        self.assert_rejected(status)

    def test_replayed_packet_is_rejected(self):
        line = self.project_line()
        created = apply_packet(self.store, self.owner, line)
        self.assert_rejected(line, DomainError)
        # Same (f,id) with different content is still the same packet id.
        self.assert_rejected(self.project_line(name="Other", step=2), DomainError)
        names = [p["name"] for p in self.store.snapshot(self.owner)["projects"]]
        self.assertEqual(names.count(created["name"]), 1)
        apply_packet(self.store, self.owner, self.project_line(name="Other", packet_id="c002", step=2))

    def test_project_create_cannot_name_an_existing_project(self):
        self.assert_rejected(self.project_line(name="New", project_hex=self.project["id"]))
        created = apply_packet(self.store, self.owner, self.project_line(name="New"))
        self.assertNotEqual(created["id"], self.project["id"])

    def test_packet_ids_are_scoped_to_sender(self):
        apply_packet(self.store, self.owner, self.project_line())
        agent = self.store.command(self.owner, "principal.create", {"name": "A", "kind": "agent"})
        self.store.command(
            self.owner, "grant.create", {"principal_id": agent["principal"]["id"], "task_id": self.task["id"], "capabilities": ["claim"]}
        )
        ctx = EncodeContext(
            packet_id="c001",
            project_hex=self.project["id"],
            task_hex=self.task["id"],
            sender_hex=agent["principal"]["id"],
            sender_human=False,
            step=1,
        )
        apply_packet(self.store, agent["token"], encode_command("task.claim", {"task_id": self.task["id"]}, ctx))


if __name__ == "__main__":
    unittest.main()
