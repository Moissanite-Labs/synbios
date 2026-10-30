"""Map forge command fields to native SYM-2P v1 surfaces (cond, ops, header)."""
from __future__ import annotations

import json
import re
from typing import Any

from .ids import sym_id

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
FORGE_BASE = "forge:v1"
COND_PREFIX = "synbios/"
# Only these cond fields carry JSON. Every other cond value is a verbatim
# string, so text that merely looks like JSON ("2024", "\"quoted\"", "true")
# survives the round trip unchanged.
JSON_COND_FIELDS = frozenset({"capabilities"})


def _cond_key(field: str, value: Any) -> str:
    if field in JSON_COND_FIELDS:
        return f"{COND_PREFIX}{field}={json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)}"
    if not isinstance(value, str):
        raise ValueError(f"cond field {field} must be a string")
    return f"{COND_PREFIX}{field}={value}"


def _parse_cond_line(line: str) -> tuple[str, Any] | None:
    if not line.startswith(COND_PREFIX):
        return None
    rest = line[len(COND_PREFIX) :]
    if "=" not in rest:
        return None
    field, raw = rest.split("=", 1)
    if field in JSON_COND_FIELDS:
        try:
            return field, json.loads(raw)
        except json.JSONDecodeError:
            pass
    return field, raw


def id_tails(hex32: str) -> tuple[str, str]:
    return hex32[:31], hex32[31]


def hex_from_sym(prefix: str, sym: str, tail: str) -> str:
    if not sym.startswith(prefix) or len(sym) != 32:
        raise ValueError("invalid sym id")
    return sym[1:] + tail


def sym_for_hex(prefix: str, hex32: str) -> tuple[str, str]:
    head, tail = id_tails(hex32)
    return prefix + head, tail


def compute_tails(action: str, payload: dict, packet: dict) -> dict[str, str]:
    tails: dict[str, str] = {}

    def note(role: str, hex_val: str | None, sym_key: str):
        if not hex_val or not _HEX32.fullmatch(hex_val):
            return
        sym = sym_id(role, hex_val)
        if sym_key and sym != sym_key:
            return
        _, tail = id_tails(hex_val)
        tails[role] = tail

    if action == "task.create":
        note("p", payload.get("project_id"), packet.get("prj"))
    if action in {"task.claim", "task.transition", "artifact.add", "evidence.add", "review.create", "grant.create"}:
        note("t", payload.get("task_id"), packet.get("tk"))
    if action == "principal.revoke":
        note("h", payload.get("principal_id"), packet.get("s"))
    return tails


def _set_op(path: str, value: str) -> dict:
    return {"op": "set", "path": path, "from": "-", "to": value}


def _add_op(path: str, value: str) -> dict:
    return {"op": "add", "path": path, "val": value}


def encode_native(action: str, payload: dict, packet: dict) -> None:
    """Attach native SYM-2P fields to packet (cond / ops / base)."""
    cond: list[str] = []
    ops: list[dict] = []

    if action == "project.create":
        cond.extend(
            [
                _cond_key("name", payload["name"]),
                _cond_key("description", payload.get("description", "")),
                _cond_key("repository", payload.get("repository", "")),
            ]
        )
    elif action == "principal.create":
        cond.extend([_cond_key("name", payload["name"]), _cond_key("kind", payload["kind"])])
    elif action == "grant.create":
        cond.extend(
            [
                _cond_key("capabilities", payload["capabilities"]),
                _cond_key("principal_id", payload["principal_id"]),
            ]
        )
    elif action == "grant.revoke":
        cond.append(_cond_key("grant_id", payload["grant_id"]))
    elif action == "task.create":
        for field in ("title", "description", "priority"):
            cond.append(_cond_key(field, payload.get(field, "" if field != "priority" else "normal")))
        for item in payload.get("criteria", []):
            ops.append(_add_op("/criteria/-", item))
        for item in payload.get("scope", []):
            ops.append(_add_op("/scope/-", item))
        for item in payload.get("dependencies", []):
            ops.append(_add_op("/dependencies/-", item))
    elif action == "task.transition":
        ops.append(_set_op("/status", payload["status"]))
    elif action == "artifact.add":
        for field in ("title", "kind", "revision", "digest", "uri", "summary"):
            ops.append(_set_op(f"/{field}", payload.get(field, "")))
    elif action == "evidence.add":
        for field in (
            "artifact_id",
            "artifact_digest",
            "revision",
            "kind",
            "status",
            "command",
            "summary",
            "tool",
            "tool_version",
        ):
            value = payload.get(field, "") if field == "command" else payload[field]
            cond.append(_cond_key(field, value))
        for item in payload.get("assumptions", []):
            cond.append(_cond_key("assumptions", item))
    elif action == "review.create":
        for field in ("artifact_id", "revision", "decision", "comment"):
            cond.append(_cond_key(field, payload.get(field, "")))

    if cond:
        packet["cond"] = cond
    if ops:
        packet["a"] = "update"
        packet["base"] = FORGE_BASE
        packet["ops"] = ops


def decode_native(action: str, packet: dict) -> dict:
    tails = {}
    ext = packet.get("ext") or {}
    syn = ext.get("synbios") or {}
    if isinstance(syn.get("tails"), dict):
        tails = {
            k: v for k, v in syn["tails"].items() if isinstance(k, str) and isinstance(v, str) and len(v) == 1
        }

    cond_values: dict[str, Any] = {}
    list_fields: dict[str, list] = {}
    for line in packet.get("cond") or []:
        if not isinstance(line, str):
            continue
        parsed = _parse_cond_line(line)
        if not parsed:
            continue
        field, value = parsed
        if field == "assumptions":
            list_fields.setdefault("assumptions", []).append(value)
        else:
            cond_values[field] = value

    ops_values: dict[str, Any] = {}
    for op in packet.get("ops") or []:
        if isinstance(op, dict) and op.get("op") == "set" and isinstance(op.get("path"), str):
            ops_values[op["path"].lstrip("/")] = op.get("to")

    list_ops: dict[str, list] = {}
    for op in packet.get("ops") or []:
        if isinstance(op, dict) and op.get("op") == "add" and isinstance(op.get("path"), str):
            field = op["path"].strip("/").split("/")[0]
            list_ops.setdefault(field, []).append(op.get("val"))

    def cv(field: str, default=None):
        if field in cond_values:
            return cond_values[field]
        if field in ops_values:
            return ops_values[field]
        if field in list_ops:
            return list_ops[field]
        return default

    if action == "project.create":
        return {
            "name": cv("name"),
            "description": cv("description", ""),
            "repository": cv("repository", ""),
        }
    if action == "principal.create":
        return {"name": cv("name"), "kind": cv("kind")}
    if action == "principal.revoke":
        return {"principal_id": _resolve_hex("h", packet.get("s"), tails)}
    if action == "grant.create":
        return {
            "principal_id": cv("principal_id"),
            "task_id": _resolve_hex("t", packet.get("tk"), tails),
            "capabilities": cv("capabilities"),
        }
    if action == "grant.revoke":
        return {"grant_id": cv("grant_id")}
    if action == "task.create":
        return {
            "project_id": _resolve_hex("p", packet.get("prj"), tails),
            "title": cv("title"),
            "description": cv("description", ""),
            "criteria": cv("criteria") or list_ops.get("criteria", []),
            "scope": cv("scope") or list_ops.get("scope", []),
            "priority": cv("priority", "normal"),
            "dependencies": cv("dependencies") or list_ops.get("dependencies", []),
        }
    if action == "task.claim":
        return {"task_id": _resolve_hex("t", packet.get("tk"), tails)}
    if action == "task.transition":
        return {
            "task_id": _resolve_hex("t", packet.get("tk"), tails),
            "status": cv("status"),
        }
    if action == "artifact.add":
        return {
            "task_id": _resolve_hex("t", packet.get("tk"), tails),
            "title": cv("title"),
            "kind": cv("kind"),
            "revision": cv("revision"),
            "digest": cv("digest"),
            "uri": cv("uri", ""),
            "summary": cv("summary", ""),
        }
    if action == "evidence.add":
        return {
            "task_id": _resolve_hex("t", packet.get("tk"), tails),
            "artifact_id": cv("artifact_id"),
            "artifact_digest": cv("artifact_digest"),
            "revision": cv("revision"),
            "kind": cv("kind"),
            "status": cv("status"),
            "command": cv("command", ""),
            "summary": cv("summary"),
            "tool": cv("tool"),
            "tool_version": cv("tool_version"),
            "assumptions": list_fields.get("assumptions", []),
        }
    if action == "review.create":
        return {
            "task_id": _resolve_hex("t", packet.get("tk"), tails),
            "artifact_id": cv("artifact_id"),
            "revision": cv("revision"),
            "decision": cv("decision"),
            "comment": cv("comment", ""),
        }
    raise ValueError("unknown command")


def _resolve_hex(role: str, sym: str | None, tails: dict) -> str:
    if not sym or role not in tails:
        raise ValueError(f"missing sym id for role {role}")
    return hex_from_sym(role, sym, tails[role])
