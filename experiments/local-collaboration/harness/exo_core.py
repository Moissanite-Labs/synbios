"""Adapter for an Exo core session (``exo serve`` / exod).

Uses only mainline Exo CLI entrypoints (``python -m exo.cli``). Requires the
``exo`` package importable on ``sys.path`` (CI installs it from GitHub; see
``handoff/bootstrap_exo.py``).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import IO

from .model import (
    CrashAmbiguityClass,
    DeclaredScopes,
    HarnessLifecycle,
    HarnessSessionState,
    ReconnectHandle,
    ScopeCheckResult,
    SessionIdentity,
)
from .pidutil import pid_is_running as _pid_portable_running

EXO_CLI = [sys.executable, "-m", "exo.cli"]

# Worker subprocess writes under workspace (separate from this process); proves observed paths.
EXO_SCOPE_WRITER = r"""
import os, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
rel = sys.argv[2]
path = root / rel.replace("/", os.sep)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("exo-scope-worker\n", encoding="utf-8")
print(path.resolve().relative_to(root).as_posix())
"""


def _exod_sock(exo_home: Path) -> Path:
    return exo_home / "run" / "exod.sock"


def _exod_pid_path(exo_home: Path) -> Path:
    return exo_home / "run" / "exod.pid"


def _probe_unix(path: Path) -> bool:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(1.0)
    try:
        client.connect(str(path))
        return True
    except OSError:
        return False
    finally:
        client.close()


def _read_pid(path: Path) -> int | None:
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


class ExoCoreHarness:
    """Manage a disposable Exo core (exod) with a dedicated ``EXO_HOME``."""

    kind = "exo-core"

    def __init__(self, workspace_root: Path, exo_home: Path):
        self.workspace_root = workspace_root.resolve()
        self.exo_home = exo_home.resolve()
        self._serve_proc: subprocess.Popen | None = None
        self._serve_log_fh: IO[bytes] | None = None
        self._session_id = uuid.uuid4().hex

    @property
    def actor_label(self) -> str:
        return f"exo-core:{self._session_id[:8]}"

    def prepare_store(self) -> None:
        """Initialize a minimal principal store under ``EXO_HOME`` (no interview, no LLM)."""
        store_root = self.exo_home / "store"
        store_root.mkdir(parents=True, exist_ok=True)
        init = subprocess.run(
            [*EXO_CLI, "init", "lc-harness", "--root", str(store_root)],
            cwd=str(self.workspace_root),
            env={**os.environ, "EXO_HOME": str(self.exo_home)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        if init.returncode != 0:
            raise RuntimeError(f"exo init failed: {init.stderr or init.stdout}")

    def start(self) -> HarnessSessionState:
        """Start ``exo serve`` in the background (socket mode)."""
        sock = _exod_sock(self.exo_home)
        sock.parent.mkdir(parents=True, exist_ok=True)
        log = self.exo_home / "logs" / "harness-exod.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self._serve_log_fh = log.open("ab", buffering=0)
        self._serve_proc = subprocess.Popen(
            [*EXO_CLI, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=self._serve_log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(self.workspace_root),
            env={
                **os.environ,
                "EXO_HOME": str(self.exo_home),
                "EXO_ENGINE": "echo",
                "PYTHONUNBUFFERED": "1",
            },
            start_new_session=True,
        )
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if _probe_unix(sock):
                pid = _read_pid(_exod_pid_path(self.exo_home))
                if pid is None:
                    raise RuntimeError("exod listening but pid file missing")
                ident = SessionIdentity(
                    harness_kind="exo-core",
                    session_id=self._session_id,
                    actor_label=self.actor_label,
                    workspace_root=self.workspace_root,
                    exo_home=self.exo_home,
                )
                return HarnessSessionState(
                    identity=ident,
                    lifecycle=HarnessLifecycle.running,
                    pid=pid,
                )
            if self._serve_proc.poll() is not None:
                tail = log.read_text(errors="replace")[-4000:] if log.exists() else ""
                self._close_log()
                raise RuntimeError(f"exo serve exited early code={self._serve_proc.returncode}\n{tail}")
            time.sleep(0.1)
        self._serve_proc.kill()
        self._serve_proc.wait(timeout=10)
        self._serve_proc = None
        self._close_log()
        raise TimeoutError("exod did not become listening")

    def _close_log(self) -> None:
        if self._serve_log_fh is not None:
            try:
                self._serve_log_fh.close()
            except OSError:
                pass
            self._serve_log_fh = None

    def stop_gracefully(self) -> str:
        proc = subprocess.run(
            [*EXO_CLI, "stop"],
            env={**os.environ, "EXO_HOME": str(self.exo_home)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        if "still shutting down" in out.lower():
            deadline = time.monotonic() + 25.0
            while time.monotonic() < deadline and self.observe_socket():
                time.sleep(0.15)
        if self._serve_proc:
            try:
                self._serve_proc.wait(timeout=25)
            except subprocess.TimeoutExpired:
                self._serve_proc.terminate()
                self._serve_proc.wait(timeout=10)
            self._serve_proc = None
        self._close_log()
        return out

    def observe_socket(self) -> bool:
        return _probe_unix(_exod_sock(self.exo_home))

    def observe_pid_alive(self, pid: int) -> bool:
        return _pid_portable_running(pid)

    def kill_exod_pid(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            if not _pid_portable_running(pid):
                break
            time.sleep(0.05)
        if self._serve_proc:
            if self._serve_proc.poll() is None:
                try:
                    self._serve_proc.send_signal(signal.SIGTERM)
                    self._serve_proc.wait(timeout=15)
                except Exception:
                    self._serve_proc.kill()
                    self._serve_proc.wait(timeout=5)
            else:
                self._serve_proc.wait(timeout=5)
            self._serve_proc = None
            self._close_log()

    def pause_exod_pid(self, pid: int) -> None:
        os.kill(pid, signal.SIGSTOP)

    def resume_exod_pid(self, pid: int) -> None:
        os.kill(pid, signal.SIGCONT)

    def reconnect_handle(self) -> ReconnectHandle:
        return ReconnectHandle(
            harness_kind="exo-core",
            exo_home=str(self.exo_home),
            socket_path=str(_exod_sock(self.exo_home)),
        )

    def verify_reconnect(self, handle: ReconnectHandle) -> bool:
        home = Path(handle.exo_home or "")
        if not home.is_dir():
            return False
        return _probe_unix(Path(handle.socket_path or _exod_sock(home)))

    def classify_crash_ambiguity(
        self,
        pid: int | None,
        *,
        hung_induced: bool = False,
        coordinator_intention_status: str | None = None,
    ) -> CrashAmbiguityClass:
        """Classify from socket + PID + optional durable coordinator row (``active`` / ``running``)."""
        from .crash_classify import classify_exo_core

        return classify_exo_core(self, pid, hung_induced=hung_induced, coordinator_intention_status=coordinator_intention_status)

    def check_scopes(self, declared: DeclaredScopes, evidence_dir: Path, *, worker_relative_path: str | None = None) -> list[ScopeCheckResult]:
        """Observe paths written by a *separate* OS process against declared writes (honest when exo cannot sandbox)."""

        evidence_dir.mkdir(parents=True, exist_ok=True)
        if not declared.writes:
            return [
                ScopeCheckResult(
                    path="",
                    allowed=False,
                    reason="no write scopes declared; cannot observe a scoped write",
                )
            ]
        if worker_relative_path is None:
            target_scope = sorted(declared.writes)[0]
            rel_target = f"{target_scope.strip().rstrip('/')}/exo_scope_worker_observed.txt"
        else:
            rel_target = worker_relative_path

        proc = subprocess.run(
            [sys.executable, "-c", EXO_SCOPE_WRITER, str(self.workspace_root), rel_target],
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        observed_rel = (proc.stdout or "").strip().splitlines()[-1] if proc.returncode == 0 else ""
        payload = {
            "declared_writes": sorted(declared.writes),
            "declared_reads": sorted(declared.reads),
            "worker_stdout_tail": (proc.stdout or "").strip(),
            "worker_stderr": (proc.stderr or "").strip(),
            "worker_exit_code": proc.returncode,
            "observed_relative_path": observed_rel,
            "worker_relative_path": rel_target,
            "note": "Path written by worker subprocess; compared to declared writes (exo main has no plan-scope sandbox to call).",
        }
        (evidence_dir / "exo_core_scope_evidence.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        if proc.returncode != 0 or not observed_rel:
            return [
                ScopeCheckResult(
                    path=rel_target,
                    allowed=False,
                    reason=f"worker failed to write (exit {proc.returncode})",
                )
            ]

        abs_path = (self.workspace_root / observed_rel).resolve()
        try:
            abs_path.relative_to(self.workspace_root)
        except ValueError:
            return [
                ScopeCheckResult(
                    path=observed_rel,
                    allowed=False,
                    reason="written path escapes workspace root",
                )
            ]
        if not abs_path.is_file():
            return [
                ScopeCheckResult(
                    path=observed_rel,
                    allowed=False,
                    reason="expected file missing after worker run",
                )
            ]

        covered = any(self._is_within(observed_rel, w) for w in declared.writes)
        return [
            ScopeCheckResult(
                path=observed_rel,
                allowed=covered,
                reason="observed file path is under declared write scope" if covered else "observed path not covered by declared write scopes",
            )
        ]

    @staticmethod
    def _is_within(rel_path: str, scope: str) -> bool:
        scope_n = scope.strip().rstrip("/")
        path_n = rel_path.strip()
        if scope_n in ("", "."):
            return True
        return path_n == scope_n or path_n.startswith(scope_n + "/")
