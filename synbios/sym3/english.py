"""Deterministic English rendering of forge commands."""
from __future__ import annotations

import json

from .canonical import canonical_payload


def render_english_lossy(action: str, payload: dict) -> str:
    """Agent-style summary prose (not information-equivalent)."""
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


def render_english_lossless(action: str, payload: dict) -> str:
    """Lossless English: every canonical field with full values."""
    p = canonical_payload(action, payload)
    if action == "project.create":
        return (
            f"Command project.create. name={p['name']!r} description={p['description']!r} "
            f"repository={p['repository']!r}."
        )
    if action == "principal.create":
        return f"Command principal.create. name={p['name']!r} kind={p['kind']!r}."
    if action == "grant.create":
        return (
            f"Command grant.create. principal_id={p['principal_id']} task_id={p['task_id']} "
            f"capabilities={json.dumps(p['capabilities'], separators=(',', ':'))}."
        )
    if action == "task.create":
        return (
            f"Command task.create. project_id={p['project_id']} title={p['title']!r} "
            f"description={p['description']!r} criteria={json.dumps(p['criteria'], separators=(',', ':'))} "
            f"scope={json.dumps(p['scope'], separators=(',', ':'))} priority={p['priority']!r} "
            f"dependencies={json.dumps(p['dependencies'], separators=(',', ':'))}."
        )
    if action == "task.claim":
        return f"Command task.claim. task_id={p['task_id']}."
    if action == "task.transition":
        return f"Command task.transition. task_id={p['task_id']} status={p['status']!r}."
    if action == "artifact.add":
        return (
            f"Command artifact.add. task_id={p['task_id']} title={p['title']!r} kind={p['kind']!r} "
            f"revision={p['revision']} digest={p['digest']} uri={p['uri']!r} summary={p['summary']!r}."
        )
    if action == "evidence.add":
        return (
            f"Command evidence.add. task_id={p['task_id']} artifact_id={p['artifact_id']} "
            f"artifact_digest={p['artifact_digest']} revision={p['revision']} kind={p['kind']!r} "
            f"status={p['status']!r} command={p['command']!r} summary={p['summary']!r} "
            f"tool={p['tool']!r} tool_version={p['tool_version']!r} "
            f"assumptions={json.dumps(p['assumptions'], separators=(',', ':'))}."
        )
    if action == "review.create":
        return (
            f"Command review.create. task_id={p['task_id']} artifact_id={p['artifact_id']} "
            f"revision={p['revision']} decision={p['decision']!r} comment={p['comment']!r}."
        )
    return f"Command {action}. {json.dumps(p, sort_keys=True, separators=(',', ':'))}."


# Back-compat alias
render_english = render_english_lossy
