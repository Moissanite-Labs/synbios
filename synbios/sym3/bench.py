#!/usr/bin/env python3
"""SYM-3 benchmark with honest decoder setup and break-even analysis."""
from __future__ import annotations

import argparse
import json
import math
import sys

from synbios.sym2p.codec import EncodeContext, encode_command

from .decoder_context import cached_setup_cost, setup_sizes
from .encoders import all_encoders, encode_transcript
from .english import render_english_lossless, render_english_lossy
from .fixtures import lifecycle_11, lifecycle_40, lifecycle_200
from .lexicon import load_lexicon
from .prior_art import (
    AGORA_ARXIV,
    agora_setup_prefix,
    encode_agora_line,
    encode_terse_english_line,
    encode_toon_line,
)
from .tokens import load_tokenizers, token_count

V2_SESSION_STEADY_TOKENS_11 = 1202
V2_SESSION_HANDSHAKE_TOTAL_11 = 1415
V2_HANDSHAKE_TOKENS_11 = V2_SESSION_HANDSHAKE_TOTAL_11 - V2_SESSION_STEADY_TOKENS_11

CACHE_ASSUMPTION = "Assumes one-time decoder prefix billed at 10% of min setup tokens (not API-measured)."
PRIMARY_NOTE = (
    "**Primary accounting** (used in break-even and verdict): total = setup (min, decode-sufficient) + messages."
)


def _sym2p_v1_lines(messages: list[tuple[str, dict]]) -> list[str]:
    project_hex = "a1" * 16
    task_hex = "b2" * 16
    sender_hex = "d4" * 16
    agent_hex = "c3" * 16
    step = 1
    lines: list[str] = []
    for index, (action, payload) in enumerate(messages, start=1):
        ctx = EncodeContext(
            packet_id=f"c{index:03d}",
            project_hex=project_hex,
            task_hex=task_hex if action not in {"project.create"} else None,
            sender_hex=sender_hex
            if action not in {"task.claim", "task.transition", "artifact.add", "evidence.add"}
            else agent_hex,
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
        lines.append(encode_command(action, payload, ctx))
    return lines


def _tok(specs, text: str) -> dict[str, int]:
    return {s.name: token_count(text, s) for s in specs}


def _primary(specs):
    return specs[0].name if specs else "n/a"


def _break_even(setup_min: float, msg_rate: float, baseline_rate: float) -> int | None:
    if msg_rate >= baseline_rate:
        return None
    need = setup_min / (baseline_rate - msg_rate)
    return int(math.ceil(need))


def _row_from_lines(
    label: str,
    lines: list[str],
    specs,
    primary: str,
    *,
    setup_min: int = 0,
    setup_full: int = 0,
) -> dict:
    blob = "\n".join(lines)
    msg_counts = _tok(specs, blob)
    msgs = msg_counts.get(primary, 0)
    cached = cached_setup_cost(setup_min)
    return {
        "label": label,
        "setup_min": {primary: setup_min},
        "setup_full": {primary: setup_full},
        "setup_cached": {primary: cached},
        "messages": msg_counts,
        "total_primary": {primary: setup_min + msgs},
        "total_full": {primary: setup_full + msgs},
        "total_cached": {primary: cached + msgs},
        "msg_rate": msgs / len(lines) if lines else 0,
        "setup_min_n": setup_min,
    }


def run_bench_for_transcript(name: str, messages: list[tuple[str, dict]]) -> dict:
    specs = load_tokenizers()
    primary = _primary(specs)
    lex = load_lexicon()
    encoders = all_encoders(lex)
    n = len(messages)

    compact_json_lines = [
        json.dumps(p, sort_keys=True, separators=(",", ":")) for _, p in messages
    ]
    pretty_json_lines = [json.dumps(p, sort_keys=True, indent=2) for _, p in messages]
    english_lossy_lines = [render_english_lossy(a, p) for a, p in messages]
    english_lossless_lines = [render_english_lossless(a, p) for a, p in messages]
    terse_lines = [encode_terse_english_line(a, p) for a, p in messages]
    toon_lines = [encode_toon_line(a, p) for a, p in messages]
    agora_lines = [encode_agora_line(a, p) for a, p in messages]
    agora_setup = agora_setup_prefix()
    agora_setup_tok = token_count(agora_setup, specs[0]) if specs else 0
    v1_lines = _sym2p_v1_lines(messages)

    rows: list[dict] = []
    rows.append(_row_from_lines("compact JSON", compact_json_lines, specs, primary))
    rows.append(_row_from_lines("pretty JSON", pretty_json_lines, specs, primary))
    rows.append(_row_from_lines("English (lossy summary)", english_lossy_lines, specs, primary))
    rows.append(_row_from_lines("English (lossless)", english_lossless_lines, specs, primary))
    rows.append(_row_from_lines("English terse (lossless, CoD-style)", terse_lines, specs, primary))
    rows.append(_row_from_lines("TOON (toon-format)", toon_lines, specs, primary))
    rows.append(
        _row_from_lines(
            f"Agora envelope (arXiv:{AGORA_ARXIV})",
            agora_lines,
            specs,
            primary,
            setup_min=agora_setup_tok,
            setup_full=agora_setup_tok,
        )
    )
    rows.append(_row_from_lines("SYM-2P v1", v1_lines, specs, primary))

    if name == "lifecycle_11":
        rows.append(
            {
                "label": "SYM-2P v2 session + handshake (PR #6)",
                "setup_min": {primary: V2_HANDSHAKE_TOKENS_11},
                "setup_full": {primary: V2_HANDSHAKE_TOKENS_11},
                "setup_cached": {primary: cached_setup_cost(V2_HANDSHAKE_TOKENS_11)},
                "messages": {primary: V2_SESSION_STEADY_TOKENS_11},
                "total_primary": {primary: V2_SESSION_HANDSHAKE_TOTAL_11},
                "total_full": {primary: V2_SESSION_HANDSHAKE_TOTAL_11},
                "total_cached": {
                    primary: cached_setup_cost(V2_HANDSHAKE_TOKENS_11) + V2_SESSION_STEADY_TOKENS_11
                },
                "note": "PR #6 dense pilot numbers",
            }
        )

    sym3_rows: list[dict] = []
    for enc_name, enc in encoders.items():
        lines = encode_transcript(enc, messages)
        sizes = setup_sizes(messages, lines, lex)
        row = _row_from_lines(
            f"SYM-3 {enc_name}",
            lines,
            specs,
            primary,
            setup_min=sizes["minimal"],
            setup_full=sizes["full"],
        )
        if enc_name == "refs":
            row["note"] = f"closest prior art: Agora (arXiv:{AGORA_ARXIV})"
        rows.append(row)
        sym3_rows.append(row)

    compact_rate = rows[0]["msg_rate"]
    english_rate = next(r["msg_rate"] for r in rows if r["label"] == "English (lossless)")
    break_even: dict[str, dict] = {}
    for row in sym3_rows:
        enc = row["label"].replace("SYM-3 ", "")
        break_even[enc] = {
            "vs_compact_json": _break_even(row["setup_min_n"], row["msg_rate"], compact_rate),
            "vs_english_lossless": _break_even(row["setup_min_n"], row["msg_rate"], english_rate),
        }

    return {
        "transcript": name,
        "count": n,
        "tokenizers": [s.name for s in specs],
        "rows": rows,
        "break_even": break_even,
    }


def format_markdown(results: list[dict], primary: str) -> str:
    lines = [
        "# SYM-3 benchmark",
        "",
        PRIMARY_NOTE,
        "Secondary: setup (full, committed lexicon + full schema). "
        f"Tertiary: setup (cached†) = 10% × setup (min). {CACHE_ASSUMPTION}",
        "",
        "Minimal setup is **decode-sufficient**: all used cmd/status/kind wire mappings and format tags "
        "for the transcript (plus all format tags when `adaptive` appears).",
        "",
    ]
    for block in results:
        lines.append(f"## {block['transcript']} ({block['count']} messages)")
        lines.append("")
        header = (
            "| Format | setup (min) | messages | total (primary) | "
            "setup (full) | total (full setup) | setup (cached†) | total (cached†) |"
        )
        sep = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        lines.extend([header, sep])
        for row in block["rows"]:
            sm = row["setup_min"].get(primary, 0)
            sf = row["setup_full"].get(primary, 0)
            sc = row["setup_cached"].get(primary, 0.0)
            msgs = row["messages"].get(primary, 0)
            tp = row["total_primary"].get(primary, sm + msgs)
            tf = row["total_full"].get(primary, sf + msgs)
            tc = row["total_cached"].get(primary, sc + msgs)
            note = row.get("note", "")
            label = row["label"] if not note else f"{row['label']} — {note}"
            lines.append(
                f"| {label} | {sm} | {msgs} | {tp} | {sf} | {tf} | {sc:.1f} | {tc:.1f} |"
            )
        lines.append("")
        lines.append("### Break-even (primary accounting: setup min + messages, o200k)")
        lines.append("")
        lines.append("| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |")
        lines.append("| --- | ---: | ---: |")
        for enc, be in sorted(block["break_even"].items()):
            c = be["vs_compact_json"]
            e = be["vs_english_lossless"]
            lines.append(
                f"| {enc} | {'never' if c is None else c} | {'never' if e is None else e} |"
            )
        lines.append("")

    lines.append("## Verdict (primary accounting, o200k_base)")
    lines.append("")
    lines.append(
        "Under **primary** totals (decode-sufficient setup min + messages), SYM-3 **refs** totals **491** vs compact JSON **682** "
        "and lossless English **686** on lifecycle_11 (wins). **Adaptive** is **512** (also below JSON). "
        "Under **full** setup (524 + messages), refs/adaptive **765** — **above** compact JSON at 11 messages. "
        "Prior-art rows: TOON **805**, terse English **691**, Agora envelope **1027** (messages-only baselines except Agora setup). "
        "SYM-3 **refs** is closest to Agora-style content addressing ([arXiv:2410.11905](https://arxiv.org/abs/2410.11905)). "
        "lifecycle_40/200 show larger wire savings; cached† totals use the 10% assumption only. "
        "Do not compare against English (lossy summary) for information equivalence."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from .reproduce import BENCH_MD, run_all_benches, verify_against_committed

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-md",
        action="store_true",
        help="Overwrite docs/sym3-bench.md (use after intentional bench changes; default is verify-only).",
    )
    args = parser.parse_args(argv)

    _results, md, _primary = run_all_benches()

    if args.write_md:
        normalized = md if md.endswith("\n") else md + "\n"
        BENCH_MD.write_text(normalized, encoding="utf-8")
        print(md)
        print(f"Wrote {BENCH_MD}")
        return 0

    verify_against_committed(md)
    print(md)
    print(f"Verified {BENCH_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
