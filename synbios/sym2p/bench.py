#!/usr/bin/env python3
"""Compare JSON API payloads, SYM-2P v1 packets, and v2 draft wire size."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from synbios.sym2p.codec import (
    EncodeContext,
    encode_command,
    status_field,
    v1_size_breakdown,
    COMMAND_ACT,
)

V2_ACT = {"assign": 1, "accept": 2, "assert": 3, "reject": 3, "update": 4}
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
    items = " ".join(
        f"{_sexpr_string(str(k))} {_sexpr_string(json.dumps(v, sort_keys=True, separators=(',', ':')))}"
        for k, v in sorted(payload.items())
    )
    return f"(33 {items})" if items else "(33)"


def encode_v2_draft(action: str, payload: dict, ctx: EncodeContext, act: str, status: str | None) -> str:
    body = f"(50 {_sexpr_string(action)} {_payload_sexpr(payload)})"
    st_code = V2_ST.get(status or "proposed", 1)
    act_code = V2_ACT.get(act, 3)
    fields = ["2", ctx.packet_id, ctx.task_sym, "6", "1", str(act_code), str(st_code), "0", "0", body, "0", "", str(ctx.step)]
    return "|".join(fields)


def lifecycle_transcript() -> list[tuple[str, dict]]:
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
    json_bytes = v1_bytes = v2_bytes = 0
    env_bytes = content_bytes = 0
    json_text: list[str] = []
    v1_text: list[str] = []
    v2_text: list[str] = []
    step = 1
    for index, (action, payload) in enumerate(lifecycle_transcript(), start=1):
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
        act = COMMAND_ACT[action]
        if action == "review.create" and payload.get("decision") == "changes_requested":
            act = "reject"
        status = status_field(action, payload)
        body_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        line_v1 = encode_command(action, payload, ctx)
        line_v2 = encode_v2_draft(action, payload, ctx, act, status)
        _, env_b, content_b = v1_size_breakdown(line_v1)
        json_bytes += len(body_json.encode("utf-8"))
        v1_bytes += len(line_v1.encode("utf-8"))
        v2_bytes += len(line_v2.encode("utf-8"))
        env_bytes += env_b
        content_bytes += content_b
        json_text.append(body_json)
        v1_text.append(line_v1)
        v2_text.append(line_v2)

    def summarize(label: str, blob: str, size: int) -> Row:
        return Row(label, size, counter(blob) if counter else None)

    combined_json = "\n".join(json_text)
    combined_v1 = "\n".join(v1_text)
    combined_v2 = "\n".join(v2_text)
    rows = [
        summarize("JSON API POST bodies", combined_json, json_bytes),
        summarize("SYM-2P v1 (Synbios codec)", combined_v1, v1_bytes),
        summarize("  v1 envelope (header + ext)", "", env_bytes),
        summarize("  v1 content (cond + ops)", "", content_bytes),
        summarize("SYM-2P v2 draft (measurement only)", combined_v2, v2_bytes),
    ]

    token_note = "tiktoken o200k_base" if counter else "tiktoken not installed; token counts omitted"
    print(f"Forge lifecycle transcript ({len(lifecycle_transcript())} commands). Tokenizer: {token_note}.")
    print(f"{'Format':<40} {'Bytes':>8} {'Tokens':>8}")
    print("-" * 58)
    for row in rows:
        tok = str(row.tokens) if row.tokens is not None else "n/a"
        if row.label.startswith("  v1"):
            env_tok = counter("\n".join(v1_text)) if counter else None
            if row.label.endswith("ext)"):
                # approximate envelope tokens as total minus content-only reconstruction
                content_lines = []
                for line in v1_text:
                    p = json.loads(line)
                    chunk = {k: p[k] for k in ("cond", "ops") if k in p}
                    if chunk:
                        content_lines.append(json.dumps(chunk, separators=(",", ":")))
                content_tok = counter("\n".join(content_lines)) if content_lines and counter else 0
                total_tok = counter(combined_v1) if counter else None
                tok = str((total_tok or 0) - (content_tok or 0)) if total_tok is not None else "n/a"
            elif row.label.endswith("ops)"):
                content_lines = []
                for line in v1_text:
                    p = json.loads(line)
                    chunk = {k: p[k] for k in ("cond", "ops") if k in p}
                    if chunk:
                        content_lines.append(json.dumps(chunk, separators=(",", ":")))
                tok = str(counter("\n".join(content_lines))) if content_lines and counter else "0"
            print(f"{row.label:<40} {row.bytes:>8} {tok:>8}")
            continue
        print(f"{row.label:<40} {row.bytes:>8} {tok:>8}")
    print()
    print("ext.synbios residue (v2 codec): cmd discriminator plus optional id tails (one hex")
    print("char per 32-byte forge id carried in tk/prj/s when the SYM header truncates).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
