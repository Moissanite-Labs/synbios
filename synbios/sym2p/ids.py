"""Map Synbios hex identifiers to SYM-2P ID grammar."""
from __future__ import annotations

import re

ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_HEX = re.compile(r"^[0-9a-f]{32}$")


def sym_id(prefix: str, hex_id: str) -> str:
    if not _HEX.fullmatch(hex_id):
        raise ValueError("expected 32-char lowercase hex id")
    if len(prefix) != 1 or not prefix.isalpha() or not prefix.islower():
        raise ValueError("prefix must be one lowercase letter")
    candidate = prefix + hex_id[:31]
    if not ID_RE.fullmatch(candidate):
        raise ValueError("could not derive SYM-2P id")
    return candidate


def forge_role(principal_id: str | None, *, human: bool) -> str:
    if principal_id and _HEX.fullmatch(principal_id):
        return sym_id("h" if human else "a", principal_id)
    return "relay" if human else "agent"
