"""S-expression body parse/render for Synbios v2 forge extensions."""
from __future__ import annotations

import json
import re

from .code_table import (
    OP_FORGE_CMD,
    OP_FORGE_FIELD,
    OP_FORGE_HEADER_F,
    OP_FORGE_HEADER_PRJ,
    OP_FORGE_KV,
    OP_FORGE_TAILS,
    OP_SESSION_BIND,
)

_SYM = re.compile(r"^(?:\*|[A-Za-z][A-Za-z0-9_./-]*)$")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tokens.append(c)
            i += 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse_body(text: str) -> tuple[list | None, str | None]:
    if not text.strip():
        return [], None
    tokens = tokenize(text)

    def parse(pos: int):
        pos += 1
        items: list = []
        while pos < len(tokens) and tokens[pos] != ")":
            if tokens[pos] == "(":
                sub, pos = parse(pos)
                items.append(sub)
            else:
                items.append(tokens[pos])
                pos += 1
        if pos >= len(tokens):
            raise ValueError("unbalanced parentheses")
        return items, pos + 1

    try:
        exprs: list = []
        pos = 0
        while pos < len(tokens):
            if tokens[pos] != "(":
                return None, "top-level atom outside expression"
            expr, pos = parse(pos)
            exprs.append(expr)
    except ValueError as ex:
        return None, str(ex)
    return exprs, None


def _sexpr_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _wire_scalar(value) -> str:
    if isinstance(value, str):
        return _sexpr_string(value)
    return _sexpr_string(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _parse_scalar(token: str):
    decoded = json.loads(str(token))
    if isinstance(decoded, str):
        try:
            inner = json.loads(decoded)
            return inner
        except json.JSONDecodeError:
            return decoded
    return decoded


def render_forge_body_raw(
    action: str,
    payload: dict,
    *,
    f_sym: str,
    prj_sym: str,
    tails: dict[str, str] | None = None,
    binds: dict[str, str] | None = None,
) -> str:
    parts = [f"(53 {_sexpr_string(f_sym)})(54 {_sexpr_string(prj_sym)})"]
    if binds:
        for role in sorted(binds):
            parts.append(f"(61 {role} {binds[role]})")
    if tails:
        for role in sorted(tails):
            parts.append(f"(56 {role} {tails[role]})")
    items = " ".join(f"{_wire_scalar(str(k))} {_wire_scalar(v)}" for k, v in sorted(payload.items()))
    payload_expr = f"(33 {items})" if items else "(33)"
    parts.append(f"(50 {_sexpr_string(action)}){payload_expr}")
    return "".join(parts)


def render_forge_body_session(action: str, payload: dict) -> str:
    from .code_table import FORGE_FIELD_INDEX

    parts = [f"(50 {_sexpr_string(action)})"]
    idx_map = FORGE_FIELD_INDEX[action]
    for field in sorted(payload.keys()):
        idx = idx_map[field]
        val = payload[field]
        parts.append(f"(51 {idx} {_wire_scalar(val)})")
    return "".join(parts)


def parse_forge_body(exprs: list, *, indexed: bool) -> tuple[str, dict, dict, dict, dict]:
    action = None
    payload: dict = {}
    header: dict = {}
    tails: dict[str, str] = {}
    binds: dict[str, str] = {}
    for expr in exprs:
        if not isinstance(expr, list) or not expr:
            raise ValueError("empty body expression")
        op = int(expr[0])
        args = expr[1:]
        if op == OP_FORGE_HEADER_F:
            if len(args) != 1:
                raise ValueError("forge header f shape")
            header["f"] = _parse_scalar(args[0])
        elif op == OP_FORGE_HEADER_PRJ:
            if len(args) != 1:
                raise ValueError("forge header prj shape")
            header["prj"] = _parse_scalar(args[0])
        elif op == OP_FORGE_TAILS:
            if len(args) != 2:
                raise ValueError("forge tails shape")
            tails[str(args[0])] = str(args[1])
        elif op == OP_SESSION_BIND and len(args) == 2 and not indexed:
            role, hex32 = str(args[0]), str(args[1])
            if role in {"p", "t", "h", "a"}:
                binds[role] = hex32
        elif op == OP_FORGE_CMD:
            if len(args) != 1:
                raise ValueError("forge cmd shape")
            action = _parse_scalar(args[0])
        elif op == OP_FORGE_KV and not indexed:
            if len(args) % 2:
                raise ValueError("forge kv pairs")
            for i in range(0, len(args), 2):
                key = _parse_scalar(args[i])
                payload[key] = _parse_scalar(args[i + 1])
        elif op == OP_FORGE_FIELD and indexed:
            if len(args) != 2:
                raise ValueError("forge field shape")
            from .code_table import _FIELD_DECODE

            if action is None:
                raise ValueError("forge field before cmd")
            idx = int(args[0])
            field = _FIELD_DECODE[action].get(idx)
            if field is None:
                raise ValueError(f"unknown field index {idx}")
            payload[field] = _parse_scalar(args[1])
        elif op == OP_FORGE_KV and indexed:
            continue
        else:
            raise ValueError(f"unexpected body opcode {op}")
    if not action:
        raise ValueError("missing forge cmd")
    return action, payload, header, tails, binds
