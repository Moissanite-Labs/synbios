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

from .model import DeclaredScopes, HarnessLifecycle, HarnessSessionState, ReconnectHandle, ScopeCheckResult, SessionIdentity


def _pid_is_running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    state = stat.rsplit(")", 1)[1].split()[0]
    return state != "Z"


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
info = {"pid": os.getpid(), "wrote": str(target)}
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

    def start(self, violate_scope: bool = False) -> HarnessSessionState:
        self._stop_flag.unlink(missing_ok=True)
        self._control.unlink(missing_ok=True)
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
        return _pid_is_running(pid)

    def kill_worker(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            if not _pid_is_running(pid):
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

    def check_scopes(self, declared: DeclaredScopes, violate: bool) -> list[ScopeCheckResult]:
        rel_name = "cli_allowed.txt"
        if violate:
            allowed = False
            reason = "write targeted path outside workspace_root (violation probe)"
            return [ScopeCheckResult(path=str(self._outside_violation), allowed=allowed, reason=reason)]

        inside = self._work / rel_name
        try:
            rel = str(inside.relative_to(self.workspace_root))
        except ValueError:
            rel = str(inside)
        ok = False
        for w in declared.writes:
            wn = w.strip().rstrip("/")
            if wn in ("", ".") or rel == wn or rel.startswith(wn + "/"):
                ok = True
                break
        return [
            ScopeCheckResult(
                path=rel,
                allowed=ok and inside.is_file(),
                reason="write under declared scope" if ok else "write path not covered by declared scopes",
            )
        ]
