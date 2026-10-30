"""SYM-2P v2 dense session context (handshake + alias resolution)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .code_table import (
    OP_SESSION_ACTOR,
    OP_SESSION_BIND,
    OP_SESSION_TABLE,
    ROLE_FORGE,
    table_hash_short,
)
from .errors import PacketRejected
from .v2_body import parse_body

_ALIAS = re.compile(r"^[a-z0-9]$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


@dataclass
class SessionContext:
    """Shared session state after a successful handshake."""

    table_hash: str
    project_hex: str
    aliases: dict[str, tuple[str, str]] = field(default_factory=dict)
    actors: dict[int, tuple[str, bool]] = field(default_factory=dict)
    handshake_id: str = ""
    handshake_seen: set[str] = field(default_factory=set)

    def require_table(self, offered: str) -> None:
        if offered != self.table_hash and offered != table_hash_short():
            raise PacketRejected("v2 code-table hash mismatch")

    def resolve_alias(self, alias: str) -> tuple[str, str]:
        if alias not in self.aliases:
            raise PacketRejected(f"unknown v2 alias {alias!r}")
        return self.aliases[alias]

    def sym_for_alias(self, alias: str) -> str:
        from .ids import sym_id

        role, hex32 = self.resolve_alias(alias)
        return sym_id(role, hex32)


def _handshake_body(
    *,
    project_hex: str,
    aliases: dict[str, tuple[str, str]],
    actors: dict[int, tuple[str, bool]],
) -> str:
    parts = [f"(60 {table_hash_short()})"]
    parts.append(f"(61 p {project_hex})")
    for alias in sorted(aliases):
        role, hex32 = aliases[alias]
        parts.append(f"(61 {alias} {role} {hex32})")
    for code in sorted(actors):
        hex32, human = actors[code]
        tag = "h" if human else "a"
        parts.append(f"(62 {code} {tag} {hex32})")
    return "".join(parts)


def build_handshake_line(
    *,
    handshake_id: str = "hs0",
    project_hex: str,
    aliases: dict[str, tuple[str, str]],
    actors: dict[int, tuple[str, bool]],
) -> str:
    body = _handshake_body(project_hex=project_hex, aliases=aliases, actors=actors)
    fields = ["2", handshake_id, ".", "0", str(ROLE_FORGE), "10", "0", "0", "0", body, "0", "", "0"]
    return "|".join(fields)


def apply_handshake(line: str, session: SessionContext) -> SessionContext:
    """Parse handshake line into session; reject replay or malformed binds."""
    parts = line.strip().split("|")
    if len(parts) != 13 or parts[0] != "2":
        raise PacketRejected("malformed v2 handshake")
    hs_id = parts[1]
    if hs_id in session.handshake_seen:
        raise PacketRejected("replayed v2 handshake")
    body = parts[9]
    exprs, err = parse_body(body)
    if err:
        raise PacketRejected(f"handshake body: {err}")
    table = None
    project = None
    aliases: dict[str, tuple[str, str]] = {}
    actors: dict[int, tuple[str, bool]] = {}
    for expr in exprs:
        if not expr or not isinstance(expr[0], str) or not expr[0].isdigit():
            raise PacketRejected("handshake opcode invalid")
        op = int(expr[0])
        args = expr[1:]
        if op == OP_SESSION_TABLE:
            if len(args) != 1:
                raise PacketRejected("session table opcode shape")
            table = str(args[0])
        elif op == OP_SESSION_BIND:
            if len(args) == 2 and args[0] == "p":
                if not _HEX32.fullmatch(str(args[1])):
                    raise PacketRejected("project bind not 32-hex")
                project = str(args[1])
            elif len(args) == 3:
                alias, role, hex32 = str(args[0]), str(args[1]), str(args[2])
                if not _ALIAS.fullmatch(alias):
                    raise PacketRejected("alias must be one lowercase alphanumeric char")
                if role not in {"p", "t", "h", "a", "e"}:
                    raise PacketRejected("invalid alias role")
                if not _HEX32.fullmatch(hex32):
                    raise PacketRejected("alias hex not 32-char lowercase")
                if alias in aliases:
                    raise PacketRejected("duplicate alias in handshake")
                aliases[alias] = (role, hex32)
            else:
                raise PacketRejected("session bind opcode shape")
        elif op == OP_SESSION_ACTOR:
            if len(args) != 3:
                raise PacketRejected("session actor opcode shape")
            code_s, tag, hex32 = str(args[0]), str(args[1]), str(args[2])
            if not code_s.isdigit():
                raise PacketRejected("actor code not integer")
            code = int(code_s)
            if code in actors:
                raise PacketRejected("duplicate actor code in handshake")
            if tag not in {"h", "a"}:
                raise PacketRejected("actor tag must be h or a")
            if not _HEX32.fullmatch(hex32):
                raise PacketRejected("actor hex not 32-char lowercase")
            actors[code] = (hex32, tag == "h")
        else:
            raise PacketRejected(f"unexpected opcode {op} in handshake")
    if table is None:
        raise PacketRejected("handshake missing code-table hash")
    if project is None:
        raise PacketRejected("handshake missing project bind")
    session.require_table(table)
    session.handshake_seen.add(hs_id)
    session.handshake_id = hs_id
    session.table_hash = table_hash_short()
    session.project_hex = project
    session.aliases = dict(aliases)
    session.actors = dict(actors)
    return session


def forge_session_from_lifecycle(
    *,
    project_hex: str,
    task_hex: str,
    actors: list[tuple[int, str, bool]],
    extra_aliases: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, SessionContext]:
    """Build default aliases for a forge transcript bench / tests."""
    aliases: dict[str, tuple[str, str]] = {
        "p": ("p", project_hex),
        "t": ("t", task_hex),
    }
    if extra_aliases:
        for key, val in extra_aliases.items():
            if key in aliases:
                raise ValueError("alias collision")
            aliases[key] = val
    actor_map = {code: (hex_id, human) for code, hex_id, human in actors}
    line = build_handshake_line(project_hex=project_hex, aliases=aliases, actors=actor_map)
    session = SessionContext(table_hash=table_hash_short(), project_hex=project_hex)
    apply_handshake(line, session)
    return line, session
