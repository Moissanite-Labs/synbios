"""Executable evidence for durable, advisory, exact-artifact negotiation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from coordinator import Coordinator
from stewardship import Stewardship


class StewardshipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "root"
        self.candidate = self.base / "candidate"
        self.root.mkdir()
        self.candidate.mkdir()
        for directory in (self.root, self.candidate):
            (directory / "a.py").write_text("old a")
            (directory / "b.py").write_text("old b")
        self.database = self.base / "weave.sqlite"
        c = Coordinator(self.database, self.root)
        self.intent = c.declare("alice", [], ["a.py"])["intention"]
        self.alternative = c.alternative(self.intent["id"], "candidate", str(self.candidate))
        c.close()
        self.s = Stewardship(self.database)
        self.addCleanup(lambda: self.s.close())
        self.charter_a = dict(capability_id="a", actor="alice", purpose="Keep a useful",
                              success_signals=["works"], failure_signals=["breaks"],
                              scope=["a.py"], peers=["b"])
        self.charter_b = dict(self.charter_a, capability_id="b", actor="bob", scope=["b.py"], peers=["a"])
        self.s.transaction("charter", self.charter_a)
        self.s.transaction("charter", self.charter_b)
        (self.candidate / "a.py").write_text("new a")
        self.p = self.propose()

    def propose(self):
        return self.s.transaction("propose", dict(actor="alice", capabilities=["a", "b"],
            intention_id=self.intent["id"], alternative_id=self.alternative["id"], rationale="Improve a with b"))

    def binding(self, actor="bob"):
        return dict(actor=actor, proposal_id=self.p["id"], proposal_digest=self.p["digest"],
                    candidate_digest=self.p["candidate_digest"])

    def support(self):
        return self.s.transaction("respond", dict(self.binding(), decision="support", comment="Reviewed exact candidate"))

    def evidence(self, outcome="passed", kind="behavior"):
        return self.s.transaction("evidence", dict(self.binding("alice"), kind=kind, outcome=outcome,
                                                  summary="Observed expected behavior; caller assertion"))

    def test_restart_and_latest_response_and_evidence(self):
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        self.support()
        self.evidence()
        self.assertTrue(self.s.check(self.p["id"])["ready"])
        self.s.close()
        self.s = Stewardship(self.database)
        self.assertTrue(self.s.resume("a")["proposals"][0]["ready"])
        self.s.transaction("respond", dict(self.binding(), decision="revise", comment="Found an issue"))
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        self.support()
        self.evidence("failed")
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        self.evidence()
        self.assertTrue(self.s.check(self.p["id"])["ready"])

    def test_candidate_change_invalidates_response_evidence_and_old_digest(self):
        self.support()
        self.evidence()
        (self.candidate / "b.py").write_text("peer surface changed")
        self.assertIn("candidate_changed", self.s.check(self.p["id"])["stale_reasons"])
        with self.assertRaises(ValueError):
            self.evidence()
        with self.assertRaises(ValueError):
            self.support()
        old = self.p
        self.p = self.propose()
        self.assertNotEqual(old["digest"], self.p["digest"])
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        with self.assertRaises(ValueError):
            self.s.transaction("respond", dict(self.binding(), candidate_digest=old["candidate_digest"],
                                                decision="support", comment="stale artifact"))

    def test_charter_scope_move_purpose_and_peer_drift(self):
        self.support()
        old_purpose = self.charter_a["purpose"]
        moved = dict(self.charter_a, scope=["moved.py"], peers=["b", "c"])
        revision = self.s.transaction("charter", moved)
        self.assertEqual(revision["revision"], 2)
        self.assertEqual(revision["purpose"], old_purpose)
        self.assertEqual(len(self.s.records("charter")), 3)
        self.assertIn("charter_changed:a", self.s.check(self.p["id"])["stale_reasons"])
        with self.assertRaises(ValueError):
            self.support()
        with self.assertRaisesRegex(ValueError, "every declared peer"):
            self.propose()

    def test_shared_baseline_and_peer_source_change(self):
        # b.py is outside the intention but inside the peer charter surface.
        (self.root / "b.py").write_text("peer source changed")
        self.assertIn("source_changed", self.s.check(self.p["id"])["stale_reasons"])
        with self.assertRaises(ValueError):
            self.support()
        (self.root / "a.py").write_text("intention changed")
        self.assertIn("baseline_stale", self.s.check(self.p["id"])["stale_reasons"])

    def test_explicit_surface_and_unverifiable_symlink(self):
        self.assertEqual(self.p["candidate_scopes"], ["a.py", "b.py"])
        (self.candidate / "unscoped.log").write_text("Not observed or claimed")
        self.assertEqual(self.s.check(self.p["id"])["stale_reasons"], [])
        (self.candidate / "a.py").unlink()
        (self.candidate / "a.py").symlink_to(self.root / "a.py")
        self.assertIn("candidate_unverifiable", self.s.check(self.p["id"])["stale_reasons"])

    def test_exact_binding_and_actor_and_rollback(self):
        original = len(self.s.records("response"))
        for changes in ({"actor": "outsider"}, {"proposal_digest": "wrong"}, {"candidate_digest": "wrong"}):
            with self.assertRaises(ValueError):
                self.s.transaction("respond", dict(self.binding(), decision="support", comment="assertion", **changes))
        self.assertEqual(len(self.s.records("response")), original)

    def test_closure_retains_failed_lesson_without_claiming_success(self):
        self.evidence("failed")
        lesson = self.s.transaction("close", dict(actor="alice", proposal_id=self.p["id"], lesson="This approach failed"))
        self.assertEqual(lesson["closure"], "not_ready")
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        self.assertEqual(len(self.s.check(self.p["id"])["lessons"]), 1)
        with self.assertRaises(ValueError):
            self.support()

    def test_ready_closure_and_inactive_intention(self):
        self.support()
        self.evidence()
        lesson = self.s.transaction("close", dict(actor="alice", proposal_id=self.p["id"], lesson="Keep exact binding"))
        self.assertEqual(lesson["closure"], "advisory_ready")
        self.s.coordinator.finish(self.intent["id"], "completed")
        self.assertIn("intention_inactive", self.s.check(self.p["id"])["stale_reasons"])

    def test_extension_preserves_existing_rows(self):
        c = self.s.coordinator
        self.assertEqual(c.get("intentions", self.intent["id"]), self.intent)
        self.assertEqual(c.get("alternatives", self.alternative["id"]), self.alternative)
        tables = {row[0] for row in self.s.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("stewardship_records", tables)
        self.assertEqual(c.status()["workspace"]["protocol"], "weave.local.v1")

    def test_analysis_cannot_replace_behavior_and_peer_failure_is_preserved(self):
        self.support()
        self.evidence(kind="analysis")
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        self.evidence()
        self.assertTrue(self.s.check(self.p["id"])["ready"])
        self.s.transaction("evidence", dict(self.binding(), kind="behavior", outcome="failed", summary="Peer found failure"))
        self.evidence()
        self.assertFalse(self.s.check(self.p["id"])["ready"])
        self.s.transaction("evidence", dict(self.binding(), kind="behavior", outcome="passed", summary="Peer rechecked"))
        self.assertTrue(self.s.check(self.p["id"])["ready"])

    def test_cli_separate_process_lifecycle(self):
        cli = Path(__file__).with_name("stewardship.py")

        def run(command, payload=None, argument=None):
            args = [sys.executable, str(cli), "--db", str(self.database), command]
            if payload is not None:
                payload_file = self.base / (command + ".json")
                payload_file.write_text(json.dumps(payload))
                args.append(str(payload_file))
            elif argument:
                args.append(argument)
            proc = subprocess.run(args, text=True, capture_output=True)
            data = json.loads(proc.stdout)
            self.assertEqual(proc.returncode, 0, data)
            return data["result"]

        p = run("propose", dict(actor="alice", capabilities=["a", "b"], intention_id=self.intent["id"],
                                 alternative_id=self.alternative["id"], rationale="Separate process negotiation"))
        binding = dict(actor="bob", proposal_id=p["id"], proposal_digest=p["digest"], candidate_digest=p["candidate_digest"])
        run("respond", dict(binding, decision="support", comment="Second session asserted review"))
        run("evidence", dict(binding, kind="behavior", outcome="passed", summary="Observed by the caller"))
        self.assertTrue(run("check", argument=p["id"])["ready"])
        self.assertEqual(len(run("resume")["proposals"]), 2)
        run("close", dict(actor="alice", proposal_id=p["id"], lesson="Durable across processes"))
        self.assertFalse(run("check", argument=p["id"])["ready"])


if __name__ == "__main__":
    unittest.main()
