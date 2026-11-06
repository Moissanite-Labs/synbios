"""Crash-ambiguity classification from observations (no dummy JSON proofs)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .model import CrashAmbiguityClass

if TYPE_CHECKING:
    from .exo_core import ExoCoreHarness


def classify_exo_core(
    h: ExoCoreHarness,
    pid: int | None,
    *,
    hung_induced: bool = False,
    coordinator_intention_status: str | None = None,
) -> CrashAmbiguityClass:
    """Use socket + PID observations plus optional coordinator row status."""
    row = (coordinator_intention_status or "").strip().lower()
    meta_active = row in ("active", "running")

    if meta_active and (pid is None or not h.observe_pid_alive(pid)):
        return CrashAmbiguityClass.metadata_claims_running

    if hung_induced and pid is not None and h.observe_pid_alive(pid):
        return CrashAmbiguityClass.process_hung

    if pid is None or not h.observe_pid_alive(pid):
        if not h.observe_socket():
            return CrashAmbiguityClass.process_gone
        return CrashAmbiguityClass.none

    return CrashAmbiguityClass.none


def classify_cli_subprocess(
    observe_pid_alive,
    pid: int | None,
    *,
    hung_induced: bool = False,
    coordinator_intention_status: str | None = None,
) -> CrashAmbiguityClass:
    """CLI harness: no socket; PID + optional coordinator metadata."""
    row = (coordinator_intention_status or "").strip().lower()
    meta_active = row in ("active", "running")

    if meta_active and (pid is None or not observe_pid_alive(pid)):
        return CrashAmbiguityClass.metadata_claims_running

    if hung_induced and pid is not None and observe_pid_alive(pid):
        return CrashAmbiguityClass.process_hung

    if pid is None or not observe_pid_alive(pid):
        return CrashAmbiguityClass.process_gone

    return CrashAmbiguityClass.none
