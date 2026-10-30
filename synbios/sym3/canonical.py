"""Canonical forge command messages for SYM-3 codecs."""
from __future__ import annotations

import copy
from typing import Any

from synbios.store import COMMAND_FIELDS

ForgeMessage = tuple[str, dict[str, Any]]

# Schema defaults applied before omit/combined encoding; decoders restore these fields.
SCHEMA_DEFAULTS: dict[str, dict[str, Any]] = {
    "project.create": {"description": "", "repository": ""},
    "principal.create": {},
    "grant.create": {},
    "task.create": {
        "description": "",
        "criteria": [],
        "scope": [],
        "priority": "normal",
        "dependencies": [],
    },
    "task.claim": {},
    "task.transition": {},
    "artifact.add": {"uri": "", "summary": ""},
    "evidence.add": {
        "assumptions": [],
    },
    "review.create": {},
}


def canonical_payload(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return payload with all command fields present and defaults filled."""
    if action not in COMMAND_FIELDS:
        raise ValueError(f"unknown forge command: {action}")
    allowed = COMMAND_FIELDS[action]
    out: dict[str, Any] = {}
    defaults = SCHEMA_DEFAULTS.get(action, {})
    merged = {**defaults, **payload}
    for key in sorted(allowed):
        if key in merged:
            out[key] = copy.deepcopy(merged[key])
        elif key in defaults:
            out[key] = copy.deepcopy(defaults[key])
        else:
            raise ValueError(f"missing required field {key!r} for {action}")
    return out


def normalize_message(action: str, payload: dict[str, Any]) -> ForgeMessage:
    return action, canonical_payload(action, payload)


def messages_equal(a: ForgeMessage, b: ForgeMessage) -> bool:
    return a[0] == b[0] and canonical_payload(a[0], a[1]) == canonical_payload(b[0], b[1])
