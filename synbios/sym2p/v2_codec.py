"""SYM-2P v2 dense wire codec (decodes to canonical v1, never bypasses validation)."""
from __future__ import annotations

import json
import re

from synbios.store import COMMAND_FIELDS

from .canonical import packet_line, parse_packet_line
from .code_table import (
    OP_SESSION_TABLE,
    ROLE_FORGE,
    V1_ACT_TO_V2,
    V1_RQ_TO_V2,
    V1_ST_TO_V2,
    V2_ACT_TO_V1,
    V2_ST_TO_V1,
    table_hash_short,
)
from .codec import EncodeContext, build_packet, decode_command
from .errors import PacketRejected
from .fields import decode_native, hex_from_sym
from .ids import forge_role, sym_id
from .session import SessionContext
from .v2_body import parse_body, parse_forge_body, render_forge_body_raw, render_forge_body_session
from .v2_wire import split_v2_fields, validate_v2_shape

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _recover_hex_from_sym(role: str, sym: str) -> str:
    for tail in "0123456789abcdef":
        candidate = sym[1:] + tail
        if _HEX32.fullmatch(candidate) and sym_id(role, candidate) == sym:
            return candidate
    raise PacketRejected(f"cannot recover hex for sym {sym!r}")


def _v1_act_st_rq(packet: dict) -> tuple[int, int, int]:
    act = V1_ACT_TO_V2.get(packet.get("a"), 3)
    st = V1_ST_TO_V2.get(packet.get("st"), 0)
    rq = V1_RQ_TO_V2.get(packet.get("rq"), 0)
    return act, st, rq


def _sender_code(packet: dict, session: SessionContext | None) -> int:
    if session:
        f_sym = packet.get("f")
        for code, (hex_id, human) in session.actors.items():
            if forge_role(hex_id, human=human) == f_sym:
                return code
        raise PacketRejected("v2 session missing actor for packet sender")
    # Raw draft: operator/coordinator placeholders from bench mapping
    return 6 if str(packet.get("f", "")).startswith("h") else 2


def _tk_token(packet: dict, session: SessionContext | None) -> str:
    if session:
        tk_sym = packet.get("tk")
        prj_sym = packet.get("prj")
        if tk_sym == prj_sym and session.sym_for_alias("p") == prj_sym:
            return "p"
        if "t" in session.aliases and session.sym_for_alias("t") == tk_sym:
            return "t"
        raise PacketRejected("v2 session cannot alias packet tk/prj")
    return packet.get("tk") or "."


def encode_v2_raw(v1_line: str) -> str:
    """Encode canonical v1 JSON line to dense v2 without session (measurement path)."""
    packet = parse_packet_line(v1_line.strip())
    action, _payload = decode_command(packet)
    full_payload = decode_native(action, packet)
    act, st, rq = _v1_act_st_rq(packet)
    ext = packet.get("ext") or {}
    syn = ext.get("synbios") or {}
    tail_map = syn.get("tails") if isinstance(syn.get("tails"), dict) else {}
    binds: dict[str, str] = {}
    if full_payload.get("project_id"):
        binds["p"] = full_payload["project_id"]
    elif "p" not in binds:
        if "p" in tail_map:
            binds["p"] = hex_from_sym("p", packet["prj"], tail_map["p"])
        else:
            binds["p"] = _recover_hex_from_sym("p", packet["prj"])
    if full_payload.get("task_id"):
        binds["t"] = full_payload["task_id"]
    elif packet.get("tk") != packet.get("prj"):
        if "t" in tail_map:
            binds["t"] = hex_from_sym("t", packet["tk"], tail_map["t"])
        else:
            binds["t"] = _recover_hex_from_sym("t", packet["tk"])
    if action == "principal.revoke":
        binds["h"] = full_payload["principal_id"]
    elif action == "grant.create":
        binds["a"] = full_payload["principal_id"]
    sender_role = "h" if str(packet["f"]).startswith("h") else "a"
    if sender_role in tail_map:
        binds[sender_role] = hex_from_sym(sender_role, packet["f"], tail_map[sender_role])
    elif sender_role not in binds:
        binds[sender_role] = _recover_hex_from_sym(sender_role, packet["f"])
    body = render_forge_body_raw(
        action,
        full_payload,
        f_sym=str(packet["f"]),
        prj_sym=str(packet["prj"]),
        tails=tail_map,
        binds=binds,
    )
    fields = [
        "2",
        str(packet["id"]),
        _tk_token(packet, None),
        str(_sender_code(packet, None)),
        "1",
        str(act),
        str(st),
        str(packet.get("cf", 0)),
        str(packet.get("cov", 0)),
        body,
        str(rq),
        str(packet.get("base", "") or ""),
        str(packet.get("exp", 0)),
    ]
    line = "|".join(fields)
    validate_v2_shape(line)
    return line


def encode_v2_session(v1_line: str, session: SessionContext) -> str:
    """Encode canonical v1 JSON line to session-aware v2."""
    packet = parse_packet_line(v1_line.strip())
    action, payload = decode_command(packet)
    act, st, rq = _v1_act_st_rq(packet)
    body = render_forge_body_session(action, payload)
    body = f"(60 {table_hash_short()})" + body
    fields = [
        "2",
        str(packet["id"]),
        _tk_token(packet, session),
        str(_sender_code(packet, session)),
        str(ROLE_FORGE),
        str(act),
        str(st),
        str(packet.get("cf", 0)),
        str(packet.get("cov", 0)),
        body,
        str(rq),
        str(packet.get("base", "") or ""),
        str(packet.get("exp", 0)),
    ]
    line = "|".join(fields)
    validate_v2_shape(line)
    return line


def _hex_from_sender(sym: str, tails: dict[str, str], binds: dict[str, str]) -> tuple[str, bool]:
    if sym.startswith("h"):
        role = "h"
        human = True
    elif sym.startswith("a"):
        role = "a"
        human = False
    else:
        raise PacketRejected("cannot derive sender hex from sym")
    if role in binds:
        return binds[role], human
    if role not in tails:
        raise PacketRejected("missing sender tail for v2 decode")
    return hex_from_sym(role, sym, tails[role]), human


def _hex_from_bind(role: str, sym: str, tails: dict[str, str], binds: dict[str, str]) -> str:
    if role in binds:
        return binds[role]
    if role not in tails:
        raise PacketRejected(f"missing {role} bind/tail for v2 decode")
    return hex_from_sym(role, sym, tails[role])


def decode_v2_to_v1(line: str, session: SessionContext | None = None) -> str:
    """Decode v2 dense line to byte-identical canonical v1 packet line."""
    fields, err = split_v2_fields(line.strip())
    if err:
        raise PacketRejected(err)
    (
        _v,
        packet_id,
        tk_tok,
        f_code,
        _t_code,
        a_code,
        st_code,
        _cf,
        _cv,
        body,
        rq_code,
        base,
        exp_s,
    ) = fields
    exprs, perr = parse_body(body)
    if perr:
        raise PacketRejected(f"v2 body: {perr}")
    indexed = session is not None
    table_seen = None
    payload_exprs: list = []
    for expr in exprs or []:
        if expr and str(expr[0]) == str(OP_SESSION_TABLE):
            table_seen = str(expr[1])
            if session:
                session.require_table(table_seen)
            continue
        payload_exprs.append(expr)
    if session and table_seen is None:
        raise PacketRejected("v2 session message missing code-table hash")
    if table_seen and session is None and table_seen != table_hash_short():
        raise PacketRejected("v2 code-table hash mismatch")
    try:
        action, payload, header, tails, binds = parse_forge_body(payload_exprs, indexed=indexed)
    except ValueError as exc:
        raise PacketRejected(str(exc)) from exc
    if action not in COMMAND_FIELDS:
        raise PacketRejected("unknown forge command in v2 body")
    missing = COMMAND_FIELDS[action] - set(payload)
    if missing:
        raise PacketRejected("v2 payload missing fields: " + ", ".join(sorted(missing)))
    step = int(exp_s)

    if session:
        if not f_code.isdigit() or int(f_code) not in session.actors:
            raise PacketRejected("unknown v2 sender actor code")
        sender_hex, human = session.actors[int(f_code)]
        project_hex = session.project_hex
        if tk_tok == "p":
            task_hex = None
        elif tk_tok == "t":
            _role, task_hex = session.resolve_alias("t")
        else:
            raise PacketRejected(f"unknown v2 alias {tk_tok!r}")
    else:
        sender_hex, human = _hex_from_sender(header["f"], tails, binds)
        project_hex = binds.get("p") or _hex_from_bind("p", header["prj"], tails, binds)
        tk_sym = tk_tok if tk_tok != "." else header["prj"]
        if tk_sym == header["prj"]:
            task_hex = None
        else:
            task_hex = binds.get("t") or _hex_from_bind("t", tk_sym, tails, binds)

    ctx = EncodeContext(
        packet_id=packet_id,
        project_hex=project_hex,
        task_hex=task_hex,
        sender_hex=sender_hex,
        sender_human=human,
        step=step,
    )
    rebuilt = build_packet(action, payload, ctx)
    return packet_line(rebuilt)


def decode_v2_roundtrip_v2(v1_line: str, session: SessionContext | None = None) -> str:
    if session:
        return encode_v2_session(v1_line, session)
    return encode_v2_raw(v1_line)


def assert_v1_roundtrip(v1_expected: str, v1_decoded: str) -> None:
    if v1_decoded != v1_expected.strip():
        raise PacketRejected("v2 decode did not reproduce canonical v1 bytes")
