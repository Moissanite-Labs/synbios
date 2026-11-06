"""Integration tests: two real harness adapters against the coordinator (filesystem + process evidence)."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

# Experiment root (parent of ``harness/``).
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "prototype"))
sys.path.insert(0, str(_ROOT))

try:
    import exo  # noqa: F401
except ImportError:
    exo = None  # type: ignore

from coordinator import Coordinator  # noqa: E402
from harness.cli_worker import CliSubprocessHarness  # noqa: E402
from harness.exo_core import ExoCoreHarness  # noqa: E402
from harness.model import CrashAmbiguityClass, DeclaredScopes  # noqa: E402


@unittest.skipIf(exo is None, "exo package not installed; run handoff/bootstrap_exo.py or CI")
class ExoCoreAdapterTests(unittest.TestCase):
    """Exo core (exod) harness: reconnect, stop, crash classes, scope evidence."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.exo_home = self.base / "exo_home"
        self.evidence = self.base / "evidence"
        self.exo_home.mkdir(parents=True)
        self.db = self.base / "coord.sqlite"
        self.coordinator = Coordinator(self.db, self.workspace)
        self.addCleanup(self.coordinator.close)

    def test_reconnect_after_stop_same_exo_home(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        h.start()
        first_handle = h.reconnect_handle()
        self.assertTrue(h.verify_reconnect(first_handle))
        h.stop_gracefully()
        self.assertFalse(h.observe_socket())
        h.start()
        self.assertTrue(h.observe_socket())
        second_handle = h.reconnect_handle()
        self.assertTrue(h.verify_reconnect(second_handle))
        h.stop_gracefully()

    def test_stop_makes_socket_dead(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        h.start()
        self.assertTrue(h.observe_socket())
        msg = h.stop_gracefully()
        deadline = time.monotonic() + 35.0
        while time.monotonic() < deadline and h.observe_socket():
            time.sleep(0.2)
        self.assertFalse(h.observe_socket(), "stop must leave exod socket non-listening; message was: " + msg)
        self.assertTrue(
            "not running" in msg.lower() or "stopped" in msg.lower() or "shutting down" in msg.lower(),
            msg,
        )

    def test_crash_ambiguity_process_gone(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        st = h.start()
        self.assertIsNotNone(st.pid)
        pid = st.pid
        assert pid is not None
        h.kill_exod_pid(pid)
        self.assertFalse(h.observe_pid_alive(pid), "process_gone: PID must not answer signals")
        self.assertFalse(h.observe_socket(), "process_gone: exod socket must not accept")
        amb = self.base / "exo_crash_ambiguity.json"
        amb.write_text(
            '{"case":"process_gone","pid_alive":false,"socket_alive":false}\n',
            encoding="utf-8",
        )
        self.assertIn("process_gone", amb.read_text())

    def test_crash_ambiguity_process_hung(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        st = h.start()
        pid = st.pid
        assert pid is not None
        h.pause_exod_pid(pid)
        try:
            self.assertTrue(h.observe_pid_alive(pid), "process_hung: stopped PID must still exist")
            amb = self.base / "exo_crash_hung.json"
            amb.write_text(
                '{"case":"process_hung","pid_alive":true,"note":"SIGSTOP stops scheduling; socket may stall"}\n',
                encoding="utf-8",
            )
        finally:
            h.resume_exod_pid(pid)
            h.stop_gracefully()

    def test_scoped_write_evidence_respected(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        h.start()
        decl = DeclaredScopes(frozenset(), frozenset(["allowed"]))
        results = h.check_scopes(decl, self.evidence)
        self.assertTrue(results, "scope check should emit evidence")
        self.assertTrue(all(r.allowed for r in results))
        ev_file = self.evidence / "exo_core_scope_evidence.json"
        self.assertTrue(ev_file.is_file())
        h.stop_gracefully()


class CliHarnessTests(unittest.TestCase):
    """CLI subprocess harness (distinct from Exo core): stop, metadata crash, scope violation."""

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
        meta_path = self.base / "crash_meta.json"
        meta_path.write_text(
            '{"crash_class":"'
            + CrashAmbiguityClass.metadata_claims_running.value
            + '","intention_status":"'
            + row["status"]
            + '","pid_dead":true}\n',
            encoding="utf-8",
        )
        self.assertIn(CrashAmbiguityClass.metadata_claims_running.value, meta_path.read_text())

    def test_scoped_violation_reported(self):
        (self.workspace / "scoped").mkdir(parents=True)
        h = CliSubprocessHarness(self.workspace)
        h.start(violate_scope=True)
        decl = DeclaredScopes(frozenset(), frozenset(["scoped"]))
        results = h.check_scopes(decl, violate=True)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].allowed)
        h.stop()


if __name__ == "__main__":
    unittest.main()
