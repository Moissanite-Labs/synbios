"""Typed harness session and crash-ambiguity vocabulary.

Illegal combinations are rejected at construction time (e.g. you cannot mark a
session ``connected`` without a process id when the adapter requires one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import FrozenSet, Literal

HarnessKind = Literal["exo-core", "cli-subprocess"]


class HarnessLifecycle(str, Enum):
    """Adapter-owned process / session lifecycle (orthogonal to weave intentions)."""

    stopped = "stopped"
    starting = "starting"
    running = "running"
    stopping = "stopping"
    disconnected = "disconnected"  # process gone; see crash class


class CrashAmbiguityClass(str, Enum):
    """External observation bucket for ``what failed`` when a harness stops answering.

    - ``process_gone``: no PID (or not our session); socket down; no hung signal.
    - ``process_hung``: PID exists but does not make progress (tests use SIGSTOP).
    - ``metadata_claims_running``: durable row still says active/running while process
      is gone or inconsistent (coordinator intention left ``active`` after kill).
    """

    none = "none"
    process_gone = "process_gone"
    process_hung = "process_hung"
    metadata_claims_running = "metadata_claims_running"


@dataclass(frozen=True)
class DeclaredScopes:
    """POSIX-relative paths under the collaboration workspace root."""

    reads: FrozenSet[str]
    writes: FrozenSet[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reads", frozenset(self.reads))
        object.__setattr__(self, "writes", frozenset(self.writes))


@dataclass(frozen=True)
class ScopeCheckResult:
    """Filesystem-backed scope enforcement report from a harness run."""

    path: str
    allowed: bool
    reason: str


@dataclass
class SessionIdentity:
    """Stable session identity for coordinator-facing actors and evidence."""

    harness_kind: HarnessKind
    session_id: str
    actor_label: str
    workspace_root: Path
    exo_home: Path | None = None  # only for exo-core


@dataclass
class ReconnectHandle:
    """Opaque token bundle for re-attachment (paths are outside the workspace tree)."""

    harness_kind: HarnessKind
    exo_home: str | None = None
    socket_path: str | None = None
    worker_control_path: str | None = None


@dataclass
class HarnessSessionState:
    """Current adapter view; persisted in memory and optionally in workspace evidence files."""

    identity: SessionIdentity
    lifecycle: HarnessLifecycle = HarnessLifecycle.stopped
    pid: int | None = None
    crash_class: CrashAmbiguityClass = CrashAmbiguityClass.none
    scope_results: list[ScopeCheckResult] = field(default_factory=list)
    last_error: str | None = None

    def snapshot(self) -> dict:
        """JSON-friendly dict for tests and logs."""
        return {
            "harness_kind": self.identity.harness_kind,
            "session_id": self.identity.session_id,
            "lifecycle": self.lifecycle.value,
            "pid": self.pid,
            "crash_class": self.crash_class.value,
            "scope_results": [
                {"path": s.path, "allowed": s.allowed, "reason": s.reason} for s in self.scope_results
            ],
            "last_error": self.last_error,
        }
