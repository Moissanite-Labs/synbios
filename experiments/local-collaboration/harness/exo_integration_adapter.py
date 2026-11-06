"""
Design-time adapter surface for Exo swarm task-contract / plan-execution PRs.

This module does **not** import the exo package. It records the integration contract version
and maps Synbios coordination scopes to the shape expected by Moissanite-Labs/exo PRs #1189–#1191
for use when those APIs are available. Wrap validators and executors there; do not reimplement them here.

See experiments/local-collaboration/DESIGN.md and coordinator.INTEGRATION_SURFACE.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_prototype = str(_ROOT / "prototype")
if _prototype not in sys.path:
    sys.path.insert(0, _prototype)

from coordinator import INTEGRATION_SURFACE, scope as normalize_scope  # noqa: E402


def contract_version():
    """Version string tests and dashboards can read."""
    return INTEGRATION_SURFACE["version"]


def swarm_references():
    """Open PR identifiers this experiment adapts against (not main-line imports yet)."""
    return dict(INTEGRATION_SURFACE["exo_swarm_design_pull_requests"])


def host_grants_payload(workspace_root, write_roots):
    """
    Map declared write scopes to lexical host roots for contract validators.

    Validators on exo #1189 expect host-relative roots; we anchor them under the workspace root string.
    """
    root = str(workspace_root).rstrip("/")
    return {
        "integration_surface": INTEGRATION_SURFACE["name"],
        "integration_surface_version": INTEGRATION_SURFACE["version"],
        "workspace_root": root,
        "write_roots": [f"{root}/{normalize_scope(w)}" for w in sorted(set(write_roots))],
    }
