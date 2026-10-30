"""Positional field order per forge command."""
from __future__ import annotations

from synbios.store import COMMAND_FIELDS

# Order used when emitting space-separated positional payloads (required fields first).
POSITIONAL_ORDER: dict[str, list[str]] = {}
for _cmd, _fields in COMMAND_FIELDS.items():
    required = sorted(_fields)
    POSITIONAL_ORDER[_cmd] = required
