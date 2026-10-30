"""Canonical SYM-2P/1.0 packet lines (SPEC.md L-3, L-4, M-2)."""
from __future__ import annotations

import json

CANON_KEY_ORDER = [
    "v", "id", "tk", "prj", "f", "t", "a", "s", "st", "cf", "err", "cov",
    "ev", "ce", "cond", "ops", "rq", "base", "exp", "auth", "ext",
]


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
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("packet must be a JSON object")
    return value
