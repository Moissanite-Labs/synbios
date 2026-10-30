"""Canonical SYM-2P/1.0 packet lines (SPEC.md L-3, L-4, M-2)."""
from __future__ import annotations

import json

CANON_KEY_ORDER = [
    "v", "id", "tk", "prj", "f", "t", "a", "s", "st", "cf", "err", "cov",
    "ev", "ce", "cond", "ops", "rq", "base", "exp", "auth", "ext",
]


class DuplicateKey(ValueError):
    def __init__(self, key):
        super().__init__(f"duplicate object key: {key!r}")
        self.key = key


def _pairs_hook(pairs):
    seen = set()
    out = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateKey(key)
        seen.add(key)
        out[key] = value
    return out


def _no_constants(name):
    raise ValueError(f"non-numeric constant {name!r} is not valid JSON")


def ordered_packet(packet: dict) -> dict:
    return {key: packet[key] for key in CANON_KEY_ORDER if key in packet}


def packet_line(packet: dict) -> str:
    return json.dumps(
        ordered_packet(packet),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def parse_packet_line(line: str) -> dict:
    line = line.strip()
    if not line:
        raise ValueError("empty packet line")
    value = json.loads(
        line,
        object_pairs_hook=_pairs_hook,
        parse_constant=_no_constants,
    )
    if not isinstance(value, dict):
        raise ValueError("packet must be a JSON object")
    return value
