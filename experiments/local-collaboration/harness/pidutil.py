"""Portable process liveness checks (Darwin + Linux + other POSIX).

Avoid relying on ``/proc`` alone: macOS TestFlight-style runs use ``run_checks.py``
without Linux ``/proc``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def pid_exists(pid: int) -> bool:
    """True if ``kill -0`` style check says the task is known to the kernel."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Another user's process; still "exists".
        return True
    return True


def pid_is_zombie(pid: int) -> bool:
    """Best-effort zombie detection for child and non-child PIDs."""
    proc = Path(f"/proc/{pid}/stat")
    if proc.is_file():
        try:
            rest = proc.read_text().rsplit(")", 1)[1]
            state = rest.split()[0]
            return state == "Z"
        except (OSError, IndexError):
            return False
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "state="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        return False
    # First column is state: Z or Z+ on some systems.
    st = line[0].strip()
    return len(st) >= 1 and st[0] == "Z"


def pid_is_running(pid: int) -> bool:
    """Process exists and is not a zombie (reapers may leave zombies briefly)."""
    return pid_exists(pid) and not pid_is_zombie(pid)
