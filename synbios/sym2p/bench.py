#!/usr/bin/env python3
"""Compare JSON API payloads, SYM-2P v1 packets, and v2 draft wire size."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from synbios.sym2p.codec import EncodeContext, encode_command

V2_ACT = {
    "assign": 1,
    "accept": 2,
    "assert": 3,
    "reject": 3,
}
V2_ST = {
    "proposed": 1,
    "assumed": 1,
    "inferred": 1,
    "verified": 4,
    "disputed": 3,
    "rejected": 3,
    "observed": 1,
}


def _sexpr_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _payload_sexpr(payload: dict) -> str:
    items = " ".join(f"{_sexpr_string(str(k))} {_sexpr_string(json.dumps(v, sort_keys=True, separators=(',', ':')))}" for k, v in sorted(payload.items()))
    return f"(33 {items})" if items else "(33)"


def encode_v2_draft(action: str, payload: dict, ctx: EncodeContext, act: str, status: str | None) -> str:
    """Measurement-only v2 draft line (SPEC-V2-DRAFT positional wire)."""
    body = f"(50 {_sexpr_string(action)} {_payload_sexpr(payload)})"
    st_code = V2_ST.get(status or "proposed", 1)
    act_code = V2_ACT.get(act, 3)
    fields = [
        "2",
        ctx.packet_id,
        ctx.task_sym,
        "6",
        "1",
        str(act_code),
        str(st_code),
        "0",
        "0",
        body,
        "0",
        "",
        str(ctx.step),
    ]
    return "|".join(fields)


def lifecycle_transcript() -> list[tuple[str, dict]]:
    """Realistic single-task forge lifecycle payloads (ids are placeholders)."""
    project = "a1" * 16
    task = "b2" * 16
    agent = "c3" * 16
    human = "d4" * 16
    artifact = "e5" * 16
    grant = "f6" * 16
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
            "summary": "Implements forge packet codec.",
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


def _token_counter():
    try:
        import tiktoken

        enc = tiktoken.get_encoding("o200k_base")
        return lambda text: len(enc.encode(text))
    except Exception:
        return None


@dataclass
class Row:
    label: str
    bytes: int
    tokens: int | None


def main() -> int:
    counter = _token_counter()
    project_hex = "a1" * 16
    task_hex = "b2" * 16
    sender_hex = "d4" * 16
    rows: list[Row] = []
    json_bytes = 0
    v1_bytes = 0
    v2_bytes = 0
    json_text = []
    v1_text = []
    v2_text = []
    step = 1
    for index, (action, payload) in enumerate(lifecycle_transcript(), start=1):
        if action == "task.create":
            pass
        ctx = EncodeContext(
            packet_id=f"c{index:03d}",
            project_hex=project_hex,
            task_hex=task_hex if action not in {"project.create"} else None,
            sender_hex=sender_hex,
            sender_human=action
            in {
                "project.create",
                "principal.create",
                "grant.create",
                "grant.revoke",
                "task.create",
                "review.create",
            },
            step=step,
        )
        step += 1
        from synbios.sym2p.codec import COMMAND_ACT, _status_field as status_field

        act = COMMAND_ACT[action]
        if action == "review.create" and payload.get("decision") == "changes_requested":
            act = "reject"
        status = status_field(action, payload)
        body_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        line_v1 = encode_command(action, payload, ctx)
        line_v2 = encode_v2_draft(action, payload, ctx, act, status)
        json_bytes += len(body_json.encode("utf-8"))
        v1_bytes += len(line_v1.encode("utf-8"))
        v2_bytes += len(line_v2.encode("utf-8"))
        json_text.append(body_json)
        v1_text.append(line_v1)
        v2_text.append(line_v2)

    def summarize(label: str, blob: str, size: int) -> Row:
        tokens = counter(blob) if counter else None
        return Row(label, size, tokens)

    combined_json = "\n".join(json_text)
    combined_v1 = "\n".join(v1_text)
    combined_v2 = "\n".join(v2_text)
    rows = [
        summarize("JSON API POST bodies", combined_json, json_bytes),
        summarize("SYM-2P v1 (Synbios codec)", combined_v1, v1_bytes),
        summarize("SYM-2P v2 draft (measurement only)", combined_v2, v2_bytes),
    ]

    token_note = "tiktoken o200k_base" if counter else "tiktoken not installed; token counts omitted"
    print(f"Forge lifecycle transcript ({len(lifecycle_transcript())} commands). Tokenizer: {token_note}.")
    print(f"{'Format':<40} {'Bytes':>8} {'Tokens':>8}")
    print("-" * 58)
    for row in rows:
        tok = str(row.tokens) if row.tokens is not None else "n/a"
        print(f"{row.label:<40} {row.bytes:>8} {tok:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
