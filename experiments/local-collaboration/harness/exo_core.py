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
    DeclaredScopes,
    HarnessLifecycle,
    HarnessSessionState,
    ReconnectHandle,
    ScopeCheckResult,
    SessionIdentity,
)

EXO_CLI = [sys.executable, "-m", "exo.cli"]


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


def _pid_is_running(pid: int) -> bool:
    """True only if the task exists and is not a zombie (``kill -0`` stays true for zombies on Linux)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    state = stat.rsplit(")", 1)[1].split()[0]
    return state != "Z"


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
        return _pid_is_running(pid)

    def kill_exod_pid(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            if not _pid_is_running(pid):
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

    def check_scopes(self, declared: DeclaredScopes, evidence_dir: Path) -> list[ScopeCheckResult]:
        """Exo does not export plan-scope enforcement on main; record declared vs workspace evidence."""
        evidence_dir.mkdir(parents=True, exist_ok=True)
        allowed_root = self.workspace_root / "allowed"
        allowed_root.mkdir(parents=True, exist_ok=True)
        sample = allowed_root / "exo-scope-smoke.txt"
        sample.write_text("scope-check\n", encoding="utf-8")
        rel = str(sample.relative_to(self.workspace_root))
        allowed_write = bool(declared.writes) and any(self._is_within(rel, w) for w in declared.writes)
        payload = {
            "declared_writes": sorted(declared.writes),
            "declared_reads": sorted(declared.reads),
            "sample_path": rel,
            "adapter_note": "exo-core adapter records declared scopes; enforcement is Exo-side when swarm APIs land",
        }
        (evidence_dir / "exo_core_scope_evidence.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        results = [
            ScopeCheckResult(
                path=rel,
                allowed=allowed_write,
                reason="written under declared write scope" if allowed_write else "no declared write covered sample path",
            )
        ]
        return results

    @staticmethod
    def _is_within(rel_path: str, scope: str) -> bool:
        scope_n = scope.strip().rstrip("/")
        path_n = rel_path.strip()
        if scope_n in ("", "."):
            return True
        return path_n == scope_n or path_n.startswith(scope_n + "/")
