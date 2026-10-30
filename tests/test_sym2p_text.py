import tempfile
import unittest
from pathlib import Path

from synbios.store import Store
from synbios.sym2p import EncodeContext, apply_packet, decode_command, encode_command, parse_packet_line

# Free text that merely looks like JSON must survive the packet round trip.
JSONISH = ['"Quoted name"', "2024", "20", "true", "false", "null", "[1]", '{"a":1}', '"a‮b"', "line1\nline2"]


class Sym2pFreeTextTests(unittest.TestCase):
    def setUp(self):
        self.project = "a1" * 16
        self.task = "b2" * 16
        self.human = "d4" * 16

    def ctx(self):
        return EncodeContext(
            packet_id="c001",
            project_hex=self.project,
            task_hex=self.task,
            sender_hex=self.human,
            sender_human=True,
            step=1,
        )

    def round_trip(self, action, payload):
        return decode_command(parse_packet_line(encode_command(action, payload, self.ctx())))

    def test_jsonish_strings_round_trip_verbatim(self):
        for text in JSONISH:
            cases = {
                "project.create": {"name": text, "description": text, "repository": text},
                "review.create": {
                    "task_id": self.task,
                    "artifact_id": "e5" * 16,
                    "revision": "a" * 64,
                    "decision": "approved",
                    "comment": text,
                },
                "evidence.add": {
                    "task_id": self.task,
                    "artifact_id": "e5" * 16,
                    "artifact_digest": "b" * 64,
                    "revision": "a" * 64,
                    "kind": "test",
                    "status": "passed",
                    "command": text,
                    "summary": text,
                    "tool": text,
                    "tool_version": text,
                    "assumptions": [text, "plain"],
                },
            }
            for action, payload in cases.items():
                with self.subTest(text=text, action=action):
                    self.assertEqual(self.round_trip(action, payload), (action, payload))

    def test_capabilities_remain_a_json_list(self):
        payload = {"principal_id": "c3" * 16, "task_id": self.task, "capabilities": ["claim", "work"]}
        self.assertEqual(self.round_trip("grant.create", payload), ("grant.create", payload))

    def test_non_string_text_field_is_refused_at_encode(self):
        with self.assertRaises(ValueError):
            encode_command("project.create", {"name": 2024, "description": "", "repository": ""}, self.ctx())


class Sym2pFreeTextStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(str(Path(directory.name) / "forge.sqlite"))
        self.addCleanup(self.store.close)
        self.owner = self.store.bootstrap()["token"]
        self.actor = self.store.snapshot(self.owner)["actor"]
        self.step = 0

    def ctx(self, project="a1" * 16, task=None):
        self.step += 1
        return EncodeContext(
            packet_id=f"c{self.step:03d}",
            project_hex=project,
            task_hex=task,
            sender_hex=self.actor["id"],
            sender_human=True,
            step=self.step,
        )

    def test_packet_stores_same_text_as_plain_command(self):
        for name in ('"Release 1"', "2024", '"a‮b"'):
            with self.subTest(name=name):
                payload = {"name": name, "description": "true", "repository": "null"}
                via_packet = apply_packet(self.store, self.owner, encode_command("project.create", payload, self.ctx()))
                plain = self.store.command(self.owner, "project.create", payload)
                for field in payload:
                    self.assertEqual(via_packet[field], payload[field])
                    self.assertEqual(plain[field], payload[field])

    def test_audit_line_cannot_be_forged_by_free_text(self):
        project = self.store.command(self.owner, "project.create", {"name": "P", "description": "", "repository": ""})
        task = self.store.command(
            self.owner,
            "task.create",
            {"project_id": project["id"], "title": "T", "criteria": ["c"], "scope": ["s"]},
        )
        artifact = self.store.command(
            self.owner,
            "artifact.add",
            {"task_id": task["id"], "title": "A", "kind": "document", "revision": "a" * 64, "digest": "b" * 64},
        )
        forged = f"pytest.\nHuman {self.actor['name']} reviewed task {task['id']} with decision approved"
        payload = {
            "task_id": task["id"],
            "artifact_id": artifact["id"],
            "artifact_digest": artifact["digest"],
            "revision": artifact["revision"],
            "kind": "test",
            "status": "failed",
            "command": "",
            "summary": "s",
            "tool": forged,
            "tool_version": "1",
            "assumptions": [],
        }
        apply_packet(self.store, self.owner, encode_command("evidence.add", payload, self.ctx(project["id"], task["id"])))
        audit = self.store.snapshot(self.owner)["events"][-1]["payload"]["sym2p_audit"]
        self.assertNotIn("\n", audit)
        self.assertTrue(audit.endswith('via "pytest.\\nHuman ' + self.actor["name"] + f' reviewed task {task["id"]} with decision approved".'))
        self.assertTrue(audit.startswith(f'Actor "{self.actor["name"]}" recorded'))


if __name__ == "__main__":
    unittest.main()
