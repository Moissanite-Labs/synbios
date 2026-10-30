"""Lifecycle fixtures for SYM-3 bench and tests."""
from __future__ import annotations

from .canonical import ForgeMessage


def lifecycle_11() -> list[ForgeMessage]:
    project = "a1" * 16
    task = "b2" * 16
    agent = "c3" * 16
    artifact = "e5" * 16
    revision = "a" * 40
    digest = "b" * 64
    return [
        ("project.create", {"name": "Commons starter", "description": "Agent-first forge pilot.", "repository": "https://example.invalid/commons"}),
        ("principal.create", {"name": "Build agent", "kind": "agent"}),
        ("principal.create", {"name": "Independent reviewer", "kind": "human"}),
        ("task.create", {
            "project_id": project,
            "title": "Wire SYM-2P codec",
            "description": "Encode forge commands as SYM-2P v1 packets.",
            "criteria": ["Round-trip lossless", "Validator exit 0"],
            "scope": ["synbios/sym2p"],
            "priority": "high",
            "dependencies": [],
        }),
        ("grant.create", {"principal_id": agent, "task_id": task, "capabilities": ["claim", "work", "artifact", "evidence", "submit"]}),
        ("task.claim", {"task_id": task}),
        ("task.transition", {"task_id": task, "status": "in_progress"}),
        ("artifact.add", {
            "task_id": task,
            "title": "SYM-2P codec module",
            "kind": "git_commit",
            "revision": revision,
            "digest": digest,
            "uri": "https://example.invalid/commit",
            "summary": "Implement forge packet codec.",
        }),
        ("evidence.add", {
            "task_id": task,
            "artifact_id": artifact,
            "artifact_digest": digest,
            "revision": revision,
            "kind": "test",
            "status": "passed",
            "command": "python -m unittest discover -s tests -v",
            "summary": "Unit tests passed locally.",
            "tool": "python",
            "tool_version": "3.11",
            "assumptions": ["Reported by agent; not executed by forge."],
        }),
        ("task.transition", {"task_id": task, "status": "in_review"}),
        ("review.create", {
            "task_id": task,
            "artifact_id": artifact,
            "revision": revision,
            "decision": "approved",
            "comment": "Independent human acceptance.",
        }),
    ]


def lifecycle_40() -> list[ForgeMessage]:
    """Extended transcript with repeated bodies, refs, and status churn."""
    base = lifecycle_11()
    project = "a1" * 16
    task = "b2" * 16
    agent = "c3" * 16
    artifact = "e5" * 16
    revision = "a" * 40
    digest = "b" * 64
    shared_spec = (
        "Acceptance criteria: round-trip all forge commands through SYM-3 encoders; "
        "bench must beat JSON on repeated large fields."
    )
    extra: list[ForgeMessage] = []
    for i in range(1, 16):
        extra.append(
            (
                "evidence.add",
                {
                    "task_id": task,
                    "artifact_id": artifact,
                    "artifact_digest": digest,
                    "revision": revision,
                    "kind": "test",
                    "status": "passed" if i % 3 else "failed",
                    "command": "python -m unittest discover -s tests -v",
                    "summary": shared_spec,
                    "tool": "python",
                    "tool_version": "3.14",
                    "assumptions": ["CI not executed in transcript."],
                },
            )
        )
    extra.append(("task.transition", {"task_id": task, "status": "in_review"}))
    extra.append(
        (
            "artifact.add",
            {
                "task_id": task,
                "title": "SYM-3 bench harness",
                "kind": "git_commit",
                "revision": revision,
                "digest": digest,
                "uri": "https://example.invalid/sym3",
                "summary": shared_spec,
            },
        )
    )
    extra.append(("grant.create", {"principal_id": agent, "task_id": task, "capabilities": ["claim", "work"]}))
    while len(base) + len(extra) < 40:
        extra.append(
            (
                "evidence.add",
                {
                    "task_id": task,
                    "artifact_id": artifact,
                    "artifact_digest": digest,
                    "revision": revision,
                    "kind": "test",
                    "status": "passed",
                    "command": "python -m unittest discover -s tests -v",
                    "summary": shared_spec,
                    "tool": "python",
                    "tool_version": "3.14",
                    "assumptions": ["Synthetic bench filler."],
                },
            )
        )
    return base + extra[: 40 - len(base)]


def lifecycle_200() -> list[ForgeMessage]:
    """Deterministic 200-message transcript: repeat lifecycle_40 segments five times."""
    chunk = lifecycle_40()
    out: list[ForgeMessage] = list(chunk)
    # Append four more full cycles (40 * 5 = 200).
    for cycle in range(1, 5):
        for action, payload in chunk:
            # Clone payload so cycles do not share mutable lists.
            cloned = {k: (list(v) if isinstance(v, list) else v) for k, v in payload.items()}
            if action == "evidence.add":
                cloned["summary"] = f"{cloned['summary']} (cycle {cycle + 1})"
            out.append((action, cloned))
    assert len(out) == 200
    return out

