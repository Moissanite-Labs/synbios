#!/usr/bin/env python3
"""Compare JSON, v1, raw v2, and session-aware v2 wire size."""
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
from synbios.sym2p.session import forge_session_from_lifecycle
from synbios.sym2p.v2_codec import encode_v2_raw, encode_v2_session


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
    agent_hex = "c3" * 16
    json_bytes = v1_bytes = v2_raw_bytes = v2_sess_bytes = 0
    hs_bytes = 0
    env_bytes = content_bytes = 0
    json_text: list[str] = []
    v1_text: list[str] = []
    v2_raw_text: list[str] = []
    v2_sess_text: list[str] = []
    step = 1
    hs_line, session = forge_session_from_lifecycle(
        project_hex=project_hex,
        task_hex=task_hex,
        actors=[
            (10, sender_hex, True),
            (11, agent_hex, False),
        ],
    )
    hs_bytes = len(hs_line.encode("utf-8"))
    commands = lifecycle_transcript()
    for index, (action, payload) in enumerate(commands, start=1):
        ctx = EncodeContext(
            packet_id=f"c{index:03d}",
            project_hex=project_hex,
            task_hex=task_hex if action not in {"project.create"} else None,
            sender_hex=sender_hex if action not in {"task.claim", "task.transition", "artifact.add", "evidence.add"} else agent_hex,
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
        body_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        line_v1 = encode_command(action, payload, ctx)
        line_v2_raw = encode_v2_raw(line_v1)
        line_v2_sess = encode_v2_session(line_v1, session)
        _, env_b, content_b = v1_size_breakdown(line_v1)
        json_bytes += len(body_json.encode("utf-8"))
        v1_bytes += len(line_v1.encode("utf-8"))
        v2_raw_bytes += len(line_v2_raw.encode("utf-8"))
        v2_sess_bytes += len(line_v2_sess.encode("utf-8"))
        env_bytes += env_b
        content_bytes += content_b
        json_text.append(body_json)
        v1_text.append(line_v1)
        v2_raw_text.append(line_v2_raw)
        v2_sess_text.append(line_v2_sess)

    n = len(commands)

    def summarize(label: str, blob: str, size: int) -> Row:
        return Row(label, size, counter(blob) if counter else None)

    combined_json = "\n".join(json_text)
    combined_v1 = "\n".join(v1_text)
    combined_v2_raw = "\n".join(v2_raw_text)
    combined_v2_sess = "\n".join(v2_sess_text)
    hs_tok = counter(hs_line) if counter else None
    sess_with_hs = combined_v2_sess + ("\n" + hs_line if combined_v2_sess else hs_line)
    rows = [
        summarize("JSON API POST bodies", combined_json, json_bytes),
        summarize("SYM-2P v1 (Synbios codec)", combined_v1, v1_bytes),
        summarize("  v1 envelope (header + ext)", "", env_bytes),
        summarize("  v1 content (cond + ops)", "", content_bytes),
        summarize("SYM-2P v2 raw (no session)", combined_v2_raw, v2_raw_bytes),
        summarize("SYM-2P v2 session (steady state)", combined_v2_sess, v2_sess_bytes),
        summarize("  v2 session handshake (once)", hs_line, hs_bytes),
        summarize(
            "  v2 session + handshake (total)",
            sess_with_hs,
            v2_sess_bytes + hs_bytes,
        ),
        summarize(
            "  v2 session amortized per msg",
            "",
            (v2_sess_bytes + hs_bytes) // n if n else 0,
        ),
    ]

    token_note = "tiktoken o200k_base" if counter else "tiktoken not installed; token counts omitted"
    print(f"Forge lifecycle transcript ({n} commands). Tokenizer: {token_note}.")
    print(f"{'Format':<40} {'Bytes':>8} {'Tokens':>8}")
    print("-" * 58)
    for row in rows:
        tok = str(row.tokens) if row.tokens is not None else "n/a"
        if row.label.startswith("  v1"):
            if row.label.endswith("ext)"):
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
        if row.label.endswith("amortized per msg") and counter:
            total_tok = counter(sess_with_hs) if counter else None
            tok = str((total_tok or 0) // n) if total_tok is not None else "n/a"
            print(f"{row.label:<40} {row.bytes:>8} {tok:>8}")
            continue
        print(f"{row.label:<40} {row.bytes:>8} {tok:>8}")
    print()
    beats = (counter(combined_json) if counter else 0) < (counter(sess_with_hs) if counter else 1)
    if counter:
        delta = counter(combined_json) - counter(sess_with_hs)
        verdict = "beats" if delta > 0 else "does not beat"
        steady = counter(combined_v2_sess)
        print(
            f"Verdict: v2 with session context {verdict} plain JSON on this transcript "
            f"({counter(combined_json)} vs {counter(sess_with_hs)} tokens incl. handshake; "
            f"steady-state {steady})."
        )
    else:
        print("Install tiktoken for token verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
