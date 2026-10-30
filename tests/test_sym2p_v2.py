import json
import tempfile
import unittest
from pathlib import Path

from synbios.store import Store, COMMAND_FIELDS
from synbios.sym2p import (
    EncodeContext,
    PacketRejected,
    apply_packet,
    apply_v2_packet,
    encode_command,
)
from synbios.sym2p.code_table import table_hash_short
from synbios.sym2p.session import SessionContext, apply_handshake, build_handshake_line, forge_session_from_lifecycle
from synbios.sym2p.v2_codec import (
    assert_v1_roundtrip,
    decode_v2_to_v1,
    encode_v2_raw,
    encode_v2_session,
    decode_v2_roundtrip_v2,
)


class Sym2pV2Tests(unittest.TestCase):
    def setUp(self):
        self.project = "a1" * 16
        self.task = "b2" * 16
        self.human = "d4" * 16
        self.agent = "c3" * 16
        self.step = 0

    def ctx(self, *, task=None, sender=None, human=True, packet_id="c001"):
        self.step += 1
        return EncodeContext(
            packet_id=packet_id,
            project_hex=self.project,
            task_hex=task or self.task,
            sender_hex=sender or self.human,
            sender_human=human,
            step=self.step,
        )

    def sample_payload(self, action):
        samples = {
            "project.create": {"name": "Lab", "description": "", "repository": ""},
            "principal.create": {"name": "Agent", "kind": "agent"},
            "principal.revoke": {"principal_id": self.human},
            "grant.create": {
                "principal_id": self.agent,
                "task_id": self.task,
                "capabilities": ["claim", "work"],
            },
            "grant.revoke": {"grant_id": "f6" * 16},
            "task.create": {
                "project_id": self.project,
                "title": "Task",
                "description": "",
                "criteria": ["Done"],
                "scope": ["src"],
                "priority": "normal",
                "dependencies": [],
            },
            "task.claim": {"task_id": self.task},
            "task.transition": {"task_id": self.task, "status": "in_progress"},
            "artifact.add": {
                "task_id": self.task,
                "title": "Patch",
                "kind": "document",
                "revision": "a" * 64,
                "digest": "b" * 64,
                "uri": "",
                "summary": "",
            },
            "evidence.add": {
                "task_id": self.task,
                "artifact_id": "e5" * 16,
                "artifact_digest": "b" * 64,
                "revision": "a" * 64,
                "kind": "test",
                "status": "passed",
                "command": "",
                "summary": "ok",
                "tool": "python",
                "tool_version": "3.11",
                "assumptions": [],
            },
            "review.create": {
                "task_id": self.task,
                "artifact_id": "e5" * 16,
                "revision": "a" * 64,
                "decision": "approved",
                "comment": "",
            },
        }
        return dict(samples[action])

    def _session(self):
        return forge_session_from_lifecycle(
            project_hex=self.project,
            task_hex=self.task,
            actors=[(10, self.human, True), (11, self.agent, False)],
        )

    def test_round_trip_raw_v2_every_command(self):
        for index, action in enumerate(COMMAND_FIELDS, start=1):
            payload = self.sample_payload(action)
            human = action in {
                "project.create",
                "principal.create",
                "principal.revoke",
                "grant.create",
                "grant.revoke",
                "task.create",
                "review.create",
            }
            v1 = encode_command(
                action,
                payload,
                self.ctx(
                    human=human,
                    sender=self.agent if action in {"task.claim", "artifact.add", "evidence.add", "task.transition"} else self.human,
                    packet_id=f"c{index:03d}",
                    task=None if action == "project.create" else self.task,
                ),
            )
            v2 = encode_v2_raw(v1)
            back = decode_v2_to_v1(v2)
            assert_v1_roundtrip(v1, back)
            self.assertEqual(encode_v2_raw(back), v2)

    def test_round_trip_session_v2_every_command(self):
        _hs, session = self._session()
        for index, action in enumerate(COMMAND_FIELDS, start=1):
            payload = self.sample_payload(action)
            human = action in {
                "project.create",
                "principal.create",
                "principal.revoke",
                "grant.create",
                "grant.revoke",
                "task.create",
                "review.create",
            }
            v1 = encode_command(
                action,
                payload,
                self.ctx(
                    human=human,
                    sender=self.agent if action in {"task.claim", "artifact.add", "evidence.add", "task.transition"} else self.human,
                    packet_id=f"c{index:03d}",
                    task=None if action == "project.create" else self.task,
                ),
            )
            v2 = encode_v2_session(v1, session)
            back = decode_v2_to_v1(v2, session)
            assert_v1_roundtrip(v1, back)
            self.assertEqual(decode_v2_roundtrip_v2(back, session), v2)

    def test_rejects_bad_table_hash(self):
        _hs, session = self._session()
        v1 = encode_command("task.claim", self.sample_payload("task.claim"), self.ctx(human=False, sender=self.agent))
        v2 = encode_v2_session(v1, session).replace(table_hash_short(), "0" * 16, 1)
        with self.assertRaises(PacketRejected):
            decode_v2_to_v1(v2, session)

    def test_rejects_unknown_alias(self):
        _hs, session = self._session()
        v1 = encode_command("task.claim", self.sample_payload("task.claim"), self.ctx(human=False, sender=self.agent))
        v2 = encode_v2_session(v1, session).replace("|t|", "|z|", 1)
        with self.assertRaises(PacketRejected):
            decode_v2_to_v1(v2, session)

    def test_rejects_truncated_v2(self):
        with self.assertRaises(PacketRejected):
            decode_v2_to_v1("2|c001|t|10|100|2|0|0|0|(50")

    def test_rejects_replayed_handshake(self):
        session = SessionContext(table_hash=table_hash_short(), project_hex=self.project)
        line = build_handshake_line(
            project_hex=self.project,
            aliases={"p": ("p", self.project), "t": ("t", self.task)},
            actors={10: (self.human, True)},
        )
        apply_handshake(line, session)
        with self.assertRaises(PacketRejected):
            apply_handshake(line, session)

    def test_apply_v2_matches_v1_path(self):
        _hs, session = self._session()
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "forge.sqlite"))
            try:
                owner = store.bootstrap()["token"]
                project = store.command(
                    owner,
                    "project.create",
                    {"name": "P", "description": "", "repository": ""},
                )
                task = store.command(
                    owner,
                    "task.create",
                    {
                        "project_id": project["id"],
                        "title": "T",
                        "description": "",
                        "criteria": ["c"],
                        "scope": ["s"],
                        "priority": "normal",
                        "dependencies": [],
                    },
                )
                hs, sess = forge_session_from_lifecycle(
                    project_hex=project["id"],
                    task_hex=task["id"],
                    actors=[(10, store.authenticate(owner)["id"], True)],
                )
                ctx = EncodeContext(
                    packet_id="c200",
                    project_hex=project["id"],
                    task_hex=task["id"],
                    sender_hex=store.authenticate(owner)["id"],
                    sender_human=True,
                    step=1,
                )
                v1 = encode_command("task.transition", {"task_id": task["id"], "status": "cancelled"}, ctx)
                v2 = encode_v2_session(v1, sess)
                result = apply_v2_packet(store, owner, v2, sess)
                self.assertEqual(result["status"], "cancelled")
                events = store.snapshot(owner)["events"]
                self.assertIn("sym2p_packet_hash", events[-1]["payload"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
