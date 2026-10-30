"""Deterministic English audit lines for SYM-2P forge packets."""
from __future__ import annotations

import json

from .canonical import parse_packet_line
from .codec import decode_command


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_audit_line(line: str) -> str:
    packet = parse_packet_line(line)
    action, payload = decode_command(line)
    actor = packet.get("f", "unknown")
    if action == "project.create":
        return f"Human {actor} created project {_quote(payload['name'])}."
    if action == "principal.create":
        return f"Human {actor} registered principal {_quote(payload['name'])} ({payload['kind']})."
    if action == "principal.revoke":
        return f"Human {actor} revoked principal {payload['principal_id']}."
    if action == "grant.create":
        caps = ", ".join(payload["capabilities"])
        return (
            f"Human {actor} granted {caps} on task {payload['task_id']} "
            f"to principal {payload['principal_id']}."
        )
    if action == "grant.revoke":
        return f"Human {actor} revoked grant {payload['grant_id']}."
    if action == "task.create":
        priority = payload.get("priority", "normal")
        return f"Human {actor} opened task {_quote(payload['title'])} (priority {priority})."
    if action == "task.claim":
        return f"Agent {actor} claimed task {payload['task_id']}."
    if action == "task.transition":
        return f"Actor {actor} moved task {payload['task_id']} to status {payload['status']}."
    if action == "artifact.add":
        return (
            f"Actor {actor} attached {payload['kind']} artifact {_quote(payload['title'])} "
            f"at revision {payload['revision'][:12]}… on task {payload['task_id']}."
        )
    if action == "evidence.add":
        return (
            f"Actor {actor} recorded {payload['kind']} evidence ({payload['status']}) "
            f"for artifact {payload['artifact_id']} on task {payload['task_id']} via {payload['tool']}."
        )
    if action == "review.create":
        return (
            f"Human {actor} reviewed task {payload['task_id']} with decision {payload['decision']} "
            f"on artifact {payload['artifact_id']}."
        )
    raise ValueError("unknown command")
