"""Apply SYM-2P packets through the forge command path."""
from __future__ import annotations

from synbios.store import Store

from .audit import render_audit_line
from .canonical import packet_line
from .codec import decode_command, packet_hash
from .errors import PacketRejected
from .ids import forge_role
from .validate import validate_wire_line


def apply_packet(store: Store, token: str, line: str):
    packet = validate_wire_line(line)
    canonical = packet_line(packet)
    if canonical != line.strip():
        raise PacketRejected("packet bytes are not canonical")
    actor = store.authenticate(token)
    expected_f = forge_role(actor["id"], human=actor["kind"] == "human")
    if packet.get("f") != expected_f:
        raise PacketRejected("packet sender f does not match authenticated actor")
    try:
        action, payload = decode_command(packet)
    except ValueError as exc:
        raise PacketRejected(str(exc)) from exc
    audit = render_audit_line(action, payload, actor)
    phash = packet_hash(packet)
    return store.command(
        token,
        action,
        payload,
        sym2p_packet_hash=phash,
        sym2p_audit=audit,
    )
