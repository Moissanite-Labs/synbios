"""Deterministic English audit lines for SYM-2P forge packets."""
from __future__ import annotations

import json


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_audit_line(action: str, payload: dict, actor: dict) -> str:
    name = actor["name"]
    if action == "project.create":
        return f"Human {name} created project {_quote(payload['name'])}."
    if action == "principal.create":
        return f"Human {name} registered principal {_quote(payload['name'])} ({payload['kind']})."
    if action == "principal.revoke":
        return f"Human {name} revoked principal {payload['principal_id']}."
    if action == "grant.create":
        caps = ", ".join(payload["capabilities"])
        return (
            f"Human {name} granted {caps} on task {payload['task_id']} "
            f"to principal {payload['principal_id']}."
        )
    if action == "grant.revoke":
        return f"Human {name} revoked grant {payload['grant_id']}."
    if action == "task.create":
        priority = payload.get("priority", "normal")
        return f"Human {name} opened task {_quote(payload['title'])} (priority {priority})."
    if action == "task.claim":
        return f"Agent {name} claimed task {payload['task_id']}."
    if action == "task.transition":
        return f"Actor {name} moved task {payload['task_id']} to status {payload['status']}."
    if action == "artifact.add":
        return (
            f"Actor {name} attached {payload['kind']} artifact {_quote(payload['title'])} "
            f"at revision {payload['revision'][:12]}… on task {payload['task_id']}."
        )
    if action == "evidence.add":
        return (
            f"Actor {name} recorded {payload['kind']} evidence ({payload['status']}) "
            f"for artifact {payload['artifact_id']} on task {payload['task_id']} via {payload['tool']}."
        )
    if action == "review.create":
        return (
            f"Human {name} reviewed task {payload['task_id']} with decision {payload['decision']} "
            f"on artifact {payload['artifact_id']}."
        )
    raise ValueError("unknown command")
