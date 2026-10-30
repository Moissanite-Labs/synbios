"""Deterministic English rendering of forge commands (agent-style prose)."""
from __future__ import annotations

from .canonical import canonical_payload


def render_english(action: str, payload: dict) -> str:
    p = canonical_payload(action, payload)
    if action == "project.create":
        return f"Create project {p['name']!r} ({p['description']}) repo {p['repository']}."
    if action == "principal.create":
        return f"Register {p['kind']} principal {p['name']!r}."
    if action == "grant.create":
        caps = ", ".join(p["capabilities"])
        return f"Grant principal {p['principal_id']} on task {p['task_id']} capabilities: {caps}."
    if action == "task.create":
        return (
            f"Create task on project {p['project_id']}: {p['title']!r} "
            f"priority {p['priority']} scope {p['scope']} criteria {p['criteria']}."
        )
    if action == "task.claim":
        return f"Claim task {p['task_id']}."
    if action == "task.transition":
        return f"Set task {p['task_id']} status to {p['status']}."
    if action == "artifact.add":
        return (
            f"Add {p['kind']} artifact {p['title']!r} on task {p['task_id']} "
            f"revision {p['revision'][:8]}… digest {p['digest'][:8]}…"
        )
    if action == "evidence.add":
        return (
            f"Record {p['kind']} evidence {p['status']} for task {p['task_id']} "
            f"via {p['tool']} {p['tool_version']}: {p['summary'][:80]}"
        )
    if action == "review.create":
        return (
            f"Review task {p['task_id']} artifact {p['artifact_id']}: "
            f"{p['decision']} — {p['comment']}"
        )
    return f"{action}: {p}"
