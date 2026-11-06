#!/usr/bin/env python3
"""Install Exo core from a pinned GitHub revision for harness integration tests.

Vendored behavior from swarm PRs #1189–#1191 is not used here; this pulls the
published ``exo`` package from Moissanite-Labs/exo main at the pin below so
``python -m exo.cli`` matches the documented first test subject.
"""

import subprocess
import sys

# Moissanite-Labs/exo main @ 2026-11-05 (see task brief).
EXO_PIN_REF = "012b1b4ba3bb10f1c322683b3a336fdb730f341f"
EXO_GIT_URL = f"git+https://github.com/Moissanite-Labs/exo.git@{EXO_PIN_REF}"


def ensure() -> None:
    try:
        import exo  # noqa: F401
        return
    except ImportError:
        pass
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", EXO_GIT_URL],
        check=True,
    )


if __name__ == "__main__":
    ensure()
    print(f"exo available (pinned {EXO_PIN_REF[:12]}…)", flush=True)
