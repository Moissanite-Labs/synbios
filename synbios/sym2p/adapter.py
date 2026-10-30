"""Apply SYM-2P packets through the forge command path."""
from __future__ import annotations

from synbios.store import Store

from .audit import render_audit_line
from .codec import decode_command, packet_hash


def apply_packet(store: Store, token: str, line: str):
    action, payload = decode_command(line)
    audit = render_audit_line(line)
    phash = packet_hash(line)
    return store.command(
        token,
        action,
        payload,
        sym2p_packet_hash=phash,
        sym2p_audit=audit,
    )
