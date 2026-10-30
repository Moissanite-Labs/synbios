"""Apply SYM-2P packets through the forge command path."""
from __future__ import annotations

from synbios.store import Store

from .audit import render_audit_line
from .canonical import packet_line
from .codec import EncodeContext, decode_command, encode_command, packet_hash
from .errors import PacketRejected
from .ids import forge_role, sym_id
from .validate import validate_wire_line


def _reencode(action: str, payload: dict, packet: dict, actor: dict) -> str:
    """The line this codec emits for the decoded command, using the received routing ids."""
    prj, tk = packet.get("prj"), packet.get("tk")
    if not isinstance(prj, str) or not isinstance(tk, str):
        raise ValueError("packet missing prj or tk")
    # Sym ids keep 31 nybbles; the 32nd never reaches the header.
    ctx = EncodeContext(
        packet_id=packet.get("id"),
        project_hex=prj[1:] + "0",
        task_hex=None if tk == prj else tk[1:] + "0",
        sender_hex=actor["id"],
        sender_human=actor["kind"] == "human",
        step=packet.get("exp"),
    )
    return encode_command(action, payload, ctx)


def apply_packet(store: Store, token: str, line: str):
    packet = validate_wire_line(line)
    canonical = packet_line(packet)
    if canonical != line.strip():
        raise PacketRejected("packet bytes are not canonical")
    snapshot = store.snapshot(token)
    actor = snapshot["actor"]
    expected_f = forge_role(actor["id"], human=actor["kind"] == "human")
    if packet.get("f") != expected_f:
        raise PacketRejected("packet sender f does not match authenticated actor")
    try:
        action, payload = decode_command(packet)
        # Header, cond and ops must say exactly what is applied: no other
        # speech act, status, subject or recipient, and no extra or repeated
        # field lines.
        if _reencode(action, payload, packet, actor) != canonical:
            raise ValueError("packet does not match the command it carries")
        task = next((t for t in snapshot["tasks"] if t["id"] == payload.get("task_id")), None)
        if task and packet["prj"] != sym_id("p", task["project_id"]):
            raise ValueError("packet prj is not the task's project")
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
        sym2p_packet_key=f"{packet['f']}/{packet['id']}",
    )
