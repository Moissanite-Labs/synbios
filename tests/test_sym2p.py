import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from synbios.store import Store, COMMAND_FIELDS, digest
from synbios.sym2p import (
    EncodeContext,
    apply_packet,
    decode_command,
    encode_command,
    packet_hash,
    render_audit_line,
)


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "vendor" / "protean-sym2p-v1.0.0" / "scripts" / "protean-sym2p" / "sym-validate.py"


class Sym2pCodecTests(unittest.TestCase):
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

    def test_round_trip_every_command(self):
        self.assertTrue(VALIDATOR.is_file())
        lines = []
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
            line = encode_command(
                action,
                payload,
                self.ctx(
                    human=human,
                    sender=self.agent if action in {"task.claim", "artifact.add", "evidence.add", "task.transition"} else self.human,
                    packet_id=f"c{index:03d}",
                ),
            )
            decoded_action, decoded_payload = decode_command(line)
            self.assertEqual(decoded_action, action)
            self.assertEqual(decoded_payload, payload)
            lines.append(line)
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write("\n".join(lines) + "\n")
            path = handle.name
        try:
            proc = subprocess.run(
                ["python3", str(VALIDATOR), path],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_audit_renderer_deterministic(self):
        payload = self.sample_payload("task.claim")
        line = encode_command("task.claim", payload, self.ctx(human=False, sender=self.agent))
        first = render_audit_line(line)
        second = render_audit_line(line)
        self.assertEqual(first, second)
        self.assertIn(self.task, first)

    def test_adapter_records_packet_hash(self):
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
                ctx = EncodeContext(
                    packet_id="c100",
                    project_hex=project["id"],
                    task_hex=task["id"],
                    sender_hex=digest({"id": store.snapshot(owner)["actor"]["id"]}),
                    sender_human=True,
                    step=1,
                )
                # Use real actor id for sender mapping
                actor = store.snapshot(owner)["actor"]
                ctx = EncodeContext(
                    packet_id="c100",
                    project_hex=project["id"],
                    task_hex=task["id"],
                    sender_hex=actor["id"],
                    sender_human=actor["kind"] == "human",
                    step=1,
                )
                line = encode_command("task.transition", {"task_id": task["id"], "status": "cancelled"}, ctx)
                apply_packet(store, owner, line)
                events = store.snapshot(owner)["events"]
                last = events[-1]
                self.assertEqual(last["payload"]["sym2p_packet_hash"], packet_hash(line))
                self.assertTrue(last["payload"]["sym2p_audit"].startswith("Actor"))
            finally:
                store.close()


    def test_lifecycle_via_packets(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "forge.sqlite"))
            try:
                owner = store.bootstrap()["token"]
                agent = store.command(owner, "principal.create", {"name": "Worker", "kind": "agent"})
                reviewer = store.command(owner, "principal.create", {"name": "Reviewer", "kind": "human"})
                project = store.command(
                    owner,
                    "project.create",
                    {"name": "Lab", "description": "", "repository": ""},
                )
                task_holder: dict[str, str] = {}
                seq = 0

                def send(action, payload, token, *, human=True):
                    nonlocal seq
                    seq += 1
                    actor = store.authenticate(token)
                    ctx = EncodeContext(
                        packet_id=f"c{seq:03d}",
                        project_hex=project["id"],
                        task_hex=payload.get("task_id") or task_holder.get("id"),
                        sender_hex=actor["id"],
                        sender_human=human,
                        step=seq,
                    )
                    line = encode_command(action, payload, ctx)
                    result = apply_packet(store, token, line)
                    if action == "task.create":
                        task_holder["id"] = result["id"]
                    return result

                task = send(
                    "task.create",
                    {
                        "project_id": project["id"],
                        "title": "Packet path",
                        "description": "",
                        "criteria": ["Accepted"],
                        "scope": ["src"],
                        "priority": "normal",
                        "dependencies": [],
                    },
                    owner,
                )
                send(
                    "grant.create",
                    {
                        "principal_id": agent["principal"]["id"],
                        "task_id": task["id"],
                        "capabilities": ["claim", "work", "artifact", "evidence", "submit"],
                    },
                    owner,
                )
                at = agent["token"]
                send("task.claim", {"task_id": task["id"]}, at, human=False)
                send("task.transition", {"task_id": task["id"], "status": "in_progress"}, at, human=False)
                revision = "a" * 40
                digest = "b" * 64
                artifact = send(
                    "artifact.add",
                    {
                        "task_id": task["id"],
                        "title": "Change",
                        "kind": "git_commit",
                        "revision": revision,
                        "digest": digest,
                        "uri": "",
                        "summary": "",
                    },
                    at,
                    human=False,
                )
                send(
                    "evidence.add",
                    {
                        "task_id": task["id"],
                        "artifact_id": artifact["id"],
                        "artifact_digest": digest,
                        "revision": revision,
                        "kind": "test",
                        "status": "passed",
                        "command": "",
                        "summary": "ok",
                        "tool": "python",
                        "tool_version": "3.11",
                        "assumptions": [],
                    },
                    at,
                    human=False,
                )
                send("task.transition", {"task_id": task["id"], "status": "in_review"}, at, human=False)
                send(
                    "review.create",
                    {
                        "task_id": task["id"],
                        "artifact_id": artifact["id"],
                        "revision": revision,
                        "decision": "approved",
                        "comment": "ok",
                    },
                    reviewer["token"],
                )
                final = store.snapshot(owner)["tasks"][0]
                self.assertEqual(final["status"], "accepted")
                packet_events = [
                    event for event in store.snapshot(owner)["events"]
                    if "sym2p_packet_hash" in event["payload"]
                ]
                self.assertEqual(len(packet_events), seq)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
