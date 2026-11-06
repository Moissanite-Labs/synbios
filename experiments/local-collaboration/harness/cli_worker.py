"""CLI subprocess harness: a distinct real OS process from Exo core.

Uses only the Python interpreter (no LLM). Writes control evidence under a
user-supplied base directory and honors cooperative stop via a flag file.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from .model import (
    CrashAmbiguityClass,
    DeclaredScopes,
    HarnessLifecycle,
    HarnessSessionState,
    ReconnectHandle,
    ScopeCheckResult,
    SessionIdentity,
)
from .pidutil import pid_is_running

WORKER_MAIN = r"""
import json, os, pathlib, time
work = pathlib.Path(os.environ["EXO_LC_WORK_DIR"])
root = pathlib.Path(os.environ["EXO_LC_WORKSPACE_ROOT"]).resolve()
stop = pathlib.Path(os.environ["EXO_LC_STOP_FLAG"])
control = pathlib.Path(os.environ["EXO_LC_CONTROL"])
viol = os.environ.get("EXO_LC_VIOLATE", "")
target = work / "cli_allowed.txt"
if viol == "1":
    target = pathlib.Path(os.environ["EXO_LC_OUTSIDE"])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("cli-worker\n", encoding="utf-8")
info = {"pid": os.getpid(), "wrote": str(target.resolve())}
control.write_text(json.dumps(info), encoding="utf-8")
while not stop.exists():
    time.sleep(0.05)
# ack shutdown
done = control.with_suffix(".done")
done.write_text(json.dumps({"pid": os.getpid(), "stopped": True}), encoding="utf-8")
control.unlink(missing_ok=True)
"""


class CliSubprocessHarness:
    """Long-running helper process with explicit stop and scope checking."""

    kind = "cli-subprocess"

    def __init__(self, workspace_root: Path, work_dir: Path | None = None):
        self.workspace_root = workspace_root.resolve()
        self._session_id = uuid.uuid4().hex
        if work_dir is None:
            self._work = (self.workspace_root / ".lc-cli-work" / self._session_id[:8]).resolve()
        else:
            self._work = work_dir.resolve()
        self._work.mkdir(parents=True, exist_ok=True)
        self._stop_flag = self._work / "stop"
        self._control = self._work / "control.json"
        self._proc: subprocess.Popen | None = None
        self._outside_violation = Path(tempfile.gettempdir()) / f"exo-lc-violation-{self._session_id}.txt"

    @property
    def actor_label(self) -> str:
        return f"cli-sub:{self._session_id[:8]}"

    @property
    def work_dir(self) -> Path:
        return self._work

    @property
    def outside_violation_path(self) -> Path:
        """Temp path used when ``violate_scope`` directs the worker outside the workspace."""
        return self._outside_violation

    def start(self, violate_scope: bool = False) -> HarnessSessionState:
        self._stop_flag.unlink(missing_ok=True)
        self._control.unlink(missing_ok=True)
        self._outside_violation.unlink(missing_ok=True)
        env = {
            **os.environ,
            "EXO_LC_WORK_DIR": str(self._work),
            "EXO_LC_WORKSPACE_ROOT": str(self.workspace_root),
            "EXO_LC_STOP_FLAG": str(self._stop_flag),
            "EXO_LC_CONTROL": str(self._control),
            "EXO_LC_VIOLATE": "1" if violate_scope else "0",
            "EXO_LC_OUTSIDE": str(self._outside_violation),
        }
        self._proc = subprocess.Popen(
            [sys.executable, "-u", "-c", WORKER_MAIN],
            env=env,
            cwd=str(self.workspace_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._control.is_file():
                data = json.loads(self._control.read_text(encoding="utf-8"))
                pid = int(data["pid"])
                ident = SessionIdentity(
                    harness_kind="cli-subprocess",
                    session_id=self._session_id,
                    actor_label=self.actor_label,
                    workspace_root=self.workspace_root,
                )
                return HarnessSessionState(identity=ident, lifecycle=HarnessLifecycle.running, pid=pid)
            if self._proc.poll() is not None:
                raise RuntimeError(f"cli worker exited early: {self._proc.returncode}")
            time.sleep(0.05)
        raise TimeoutError("cli worker did not publish control")

    def stop(self) -> None:
        self._stop_flag.write_text("stop\n", encoding="utf-8")
        if self._proc:
            self._proc.wait(timeout=20)
            self._proc = None

    def observe_pid_alive(self, pid: int) -> bool:
        return pid_is_running(pid)

    def kill_worker(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            if not pid_is_running(pid):
                break
            time.sleep(0.05)
        if self._proc:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
            self._proc = None

    def pause_worker(self, pid: int) -> None:
        os.kill(pid, signal.SIGSTOP)

    def resume_worker(self, pid: int) -> None:
        os.kill(pid, signal.SIGCONT)

    def reconnect_handle(self) -> ReconnectHandle:
        return ReconnectHandle(
            harness_kind="cli-subprocess",
            worker_control_path=str(self._control),
        )

    def classify_crash_ambiguity(
        self,
        pid: int | None,
        *,
        hung_induced: bool = False,
        coordinator_intention_status: str | None = None,
    ) -> CrashAmbiguityClass:
        from .crash_classify import classify_cli_subprocess

        return classify_cli_subprocess(
            self.observe_pid_alive,
            pid,
            hung_induced=hung_induced,
            coordinator_intention_status=coordinator_intention_status,
        )

    def check_scopes(self, declared: DeclaredScopes) -> list[ScopeCheckResult]:
        """Inspect ``control.json`` ``wrote`` path: filesystem evidence vs workspace root and declared writes."""
        if not self._control.is_file():
            return [ScopeCheckResult(path="", allowed=False, reason="control.json missing; no observed write")]
        try:
            data = json.loads(self._control.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return [ScopeCheckResult(path="", allowed=False, reason=f"control unreadable: {exc}")]

        wrote = data.get("wrote")
        if not wrote:
            return [ScopeCheckResult(path="", allowed=False, reason="control has no wrote path")]

        path = Path(wrote).resolve()
        if not path.is_file():
            return [ScopeCheckResult(path=str(path), allowed=False, reason="wrote path is not a file")]

        try:
            rel = str(path.relative_to(self.workspace_root))
        except ValueError:
            return [
                ScopeCheckResult(
                    path=str(path),
                    allowed=False,
                    reason="file written outside workspace_root (not covered by collaboration root)",
                )
            ]

        covered = any(self._is_within(rel, w) for w in declared.writes)
        return [
            ScopeCheckResult(
                path=rel,
                allowed=covered,
                reason="observed path is under declared write scopes"
                if covered
                else "observed path is inside workspace but not covered by declared write scopes",
            )
        ]

    @staticmethod
    def _is_within(rel_path: str, scope: str) -> bool:
        scope_n = scope.strip().rstrip("/")
        path_n = rel_path.strip()
        if scope_n in ("", "."):
            return True
        return path_n == scope_n or path_n.startswith(scope_n + "/")
