"""Exo core adapter tests (require ``exo`` package; CI runs ``bootstrap_exo.py`` first)."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "prototype"))
sys.path.insert(0, str(_ROOT))

try:
    import exo  # noqa: F401
except ImportError:
    exo = None  # type: ignore

from harness.exo_core import ExoCoreHarness  # noqa: E402
from harness.model import CrashAmbiguityClass, DeclaredScopes  # noqa: E402


@unittest.skipIf(exo is None, "exo package not installed; run handoff/bootstrap_exo.py before these tests")
class ExoCoreAdapterTests(unittest.TestCase):
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
        pid = st.pid
        assert pid is not None
        h.kill_exod_pid(pid)
        self.assertEqual(
            h.classify_crash_ambiguity(pid),
            CrashAmbiguityClass.process_gone,
        )

    def test_crash_ambiguity_process_hung(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        st = h.start()
        pid = st.pid
        assert pid is not None
        h.pause_exod_pid(pid)
        try:
            self.assertEqual(
                h.classify_crash_ambiguity(pid, hung_induced=True),
                CrashAmbiguityClass.process_hung,
            )
        finally:
            h.resume_exod_pid(pid)
            h.stop_gracefully()

    def test_scoped_write_respect_observed(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        h.start()
        decl = DeclaredScopes(frozenset(), frozenset(["allowed"]))
        results = h.check_scopes(decl, self.evidence)
        self.assertTrue(results and results[0].allowed, results[0].reason if results else "no results")
        self.assertTrue((self.evidence / "exo_core_scope_evidence.json").is_file())
        h.stop_gracefully()

    def test_scoped_write_violation_observed(self):
        h = ExoCoreHarness(self.workspace, self.exo_home)
        h.prepare_store()
        h.start()
        decl = DeclaredScopes(frozenset(), frozenset(["allowed"]))
        results = h.check_scopes(decl, self.evidence, worker_relative_path="forbidden/forbidden_write.txt")
        self.assertTrue(results and not results[0].allowed, results[0].reason if results else "")
        h.stop_gracefully()


if __name__ == "__main__":
    unittest.main()
