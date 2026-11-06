"""CLI subprocess adapter tests (no Exo dependency; portable suite)."""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "prototype"))
sys.path.insert(0, str(_ROOT))

from coordinator import Coordinator  # noqa: E402
from harness.cli_worker import CliSubprocessHarness  # noqa: E402
from harness.model import CrashAmbiguityClass, DeclaredScopes  # noqa: E402


class CliHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.db = self.base / "coord.sqlite"
        self.coordinator = Coordinator(self.db, self.workspace)
        self.addCleanup(self.coordinator.close)

    def test_reconnect_same_work_dir(self):
        fixed = self.workspace / ".reconnect-cli"
        fixed.mkdir(parents=True)
        h = CliSubprocessHarness(self.workspace, work_dir=fixed)
        h.start()
        handle = h.reconnect_handle()
        self.assertTrue(Path(handle.worker_control_path or "").is_file())
        h.stop()
        h2 = CliSubprocessHarness(self.workspace, work_dir=fixed)
        h2.start()
        self.assertTrue(Path(handle.worker_control_path or "").is_file())
        h2.stop()

    def test_stop_flag_stops_worker(self):
        h = CliSubprocessHarness(self.workspace)
        st = h.start()
        self.assertIsNotNone(st.pid)
        self.assertTrue(h.observe_pid_alive(st.pid))  # type: ignore[arg-type]
        h.stop()
        self.assertFalse(h.observe_pid_alive(st.pid))  # type: ignore[arg-type]

    def test_crash_ambiguity_process_gone(self):
        h = CliSubprocessHarness(self.workspace)
        st = h.start()
        pid = st.pid
        assert pid is not None
        h.kill_worker(pid)
        self.assertEqual(h.classify_crash_ambiguity(pid), CrashAmbiguityClass.process_gone)

    def test_crash_ambiguity_process_hung(self):
        h = CliSubprocessHarness(self.workspace)
        st = h.start()
        pid = st.pid
        assert pid is not None
        h.pause_worker(pid)
        try:
            self.assertEqual(
                h.classify_crash_ambiguity(pid, hung_induced=True),
                CrashAmbiguityClass.process_hung,
            )
        finally:
            h.resume_worker(pid)
            h.stop()

    def test_crash_ambiguity_metadata_claims_running(self):
        scoped = self.workspace / "scoped"
        scoped.mkdir(parents=True)
        work = self.workspace / ".cli-meta"
        work.mkdir(parents=True)
        h = CliSubprocessHarness(self.workspace, work_dir=work)
        st = h.start()
        actor = f"{h.actor_label}-{uuid.uuid4().hex[:6]}"
        intention = self.coordinator.declare(actor, ["scoped"], ["scoped"])["intention"]
        h.kill_worker(st.pid)  # type: ignore[arg-type]
        row = self.coordinator.get("intentions", intention["id"])
        self.assertEqual(row["status"], "active")
        self.assertFalse(h.observe_pid_alive(st.pid))  # type: ignore[arg-type]
        self.assertEqual(
            h.classify_crash_ambiguity(st.pid, coordinator_intention_status=row["status"]),
            CrashAmbiguityClass.metadata_claims_running,
        )

    def test_scoped_respects_declared_writes(self):
        h = CliSubprocessHarness(self.workspace)
        h.start(violate_scope=False)
        decl = DeclaredScopes(frozenset(), frozenset([".lc-cli-work"]))
        results = h.check_scopes(decl)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].allowed, results[0].reason)
        h.stop()

    def test_scoped_violation_observed_outside_workspace(self):
        (self.workspace / "scoped").mkdir(parents=True)
        h = CliSubprocessHarness(self.workspace)
        h.start(violate_scope=True)
        decl = DeclaredScopes(frozenset(), frozenset(["scoped"]))
        results = h.check_scopes(decl)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].allowed)
        self.assertTrue(h.outside_violation_path.is_file())  # type: ignore[attr-defined]
        h.stop()


if __name__ == "__main__":
    unittest.main()
