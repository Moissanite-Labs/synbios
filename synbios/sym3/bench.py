#!/usr/bin/env python3
"""SYM-3 benchmark with honest decoder setup and break-even analysis."""
from __future__ import annotations

import json
import math
import sys

from synbios.sym2p.codec import EncodeContext, encode_command

from .decoder_context import cached_setup_cost, setup_sizes
from .encoders import all_encoders, encode_transcript
from .english import render_english_lossless, render_english_lossy
from .fixtures import lifecycle_11, lifecycle_40, lifecycle_200
from .lexicon import load_lexicon
from .tokens import load_tokenizers, token_count

V2_SESSION_STEADY_TOKENS_11 = 1202
V2_SESSION_HANDSHAKE_TOTAL_11 = 1415
V2_HANDSHAKE_TOKENS_11 = V2_SESSION_HANDSHAKE_TOTAL_11 - V2_SESSION_STEADY_TOKENS_11

CACHE_ASSUMPTION = "Assumes one-time decoder prefix billed at 10% of input token price (not measured on an API)."


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


def run_bench_for_transcript(name: str, messages: list[tuple[str, dict]]) -> dict:
    specs = load_tokenizers()
    primary = _primary(specs)
    lex = load_lexicon()
    encoders = all_encoders(lex)

    compact_json_lines = [
        json.dumps(p, sort_keys=True, separators=(",", ":")) for _, p in messages
    ]
    pretty_json_lines = [json.dumps(p, sort_keys=True, indent=2) for _, p in messages]
    english_lossy_lines = [render_english_lossy(a, p) for a, p in messages]
    english_lossless_lines = [render_english_lossless(a, p) for a, p in messages]
    v1_lines = _sym2p_v1_lines(messages)
    n = len(messages)

    rows: list[dict] = []

    def add_baseline(label: str, lines: list[str]) -> None:
        blob = "\n".join(lines)
        counts = _tok(specs, blob)
        rows.append(
            {
                "label": label,
                "setup_full": {primary: 0},
                "setup_min": {primary: 0},
                "setup_cached": {primary: 0.0},
                "messages": counts,
                "total_full": dict(counts),
                "total_cached": dict(counts),
            }
        )

    add_baseline("compact JSON", compact_json_lines)
    add_baseline("pretty JSON", pretty_json_lines)
    add_baseline("English (lossy summary)", english_lossy_lines)
    add_baseline("English (lossless)", english_lossless_lines)
    add_baseline("SYM-2P v1", v1_lines)

    if name == "lifecycle_11":
        rows.append(
            {
                "label": "SYM-2P v2 session + handshake (PR #6)",
                "setup_full": {primary: V2_HANDSHAKE_TOKENS_11},
                "setup_min": {primary: V2_HANDSHAKE_TOKENS_11},
                "setup_cached": {primary: cached_setup_cost(V2_HANDSHAKE_TOKENS_11)},
                "messages": {primary: V2_SESSION_STEADY_TOKENS_11},
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
        blob = "\n".join(lines)
        msg_counts = _tok(specs, blob)
        setup_full_n = sizes["full"]
        setup_min_n = sizes["minimal"]
        cached_n = cached_setup_cost(setup_min_n)
        row = {
            "label": f"SYM-3 {enc_name}",
            "setup_full": {primary: setup_full_n},
            "setup_min": {primary: setup_min_n},
            "setup_cached": {primary: cached_n},
            "messages": msg_counts,
            "total_full": {primary: setup_full_n + msg_counts.get(primary, 0)},
            "total_cached": {primary: cached_n + msg_counts.get(primary, 0)},
            "msg_rate": msg_counts.get(primary, 0) / n if n else 0,
            "setup_min_n": setup_min_n,
        }
        rows.append(row)
        sym3_rows.append(row)

    compact_rate = rows[0]["messages"].get(primary, 0) / n if n else 0
    english_rate = next(r["messages"].get(primary, 0) / n for r in rows if r["label"] == "English (lossless)") if n else 0
    break_even: dict[str, dict] = {}
    for row in sym3_rows:
        enc = row["label"].replace("SYM-3 ", "")
        rate = row["msg_rate"]
        smin = row["setup_min_n"]
        break_even[enc] = {
            "vs_compact_json": _break_even(smin, rate, compact_rate),
            "vs_english_lossless": _break_even(smin, rate, english_rate),
        }

    return {
        "transcript": name,
        "count": n,
        "tokenizers": [s.name for s in specs],
        "rows": rows,
        "break_even": break_even,
        "rates": {
            "compact_json": compact_rate,
            "english_lossless": english_rate,
        },
    }


def run_break_even_200(specs, primary: str) -> dict:
    messages = lifecycle_200()
    lex = load_lexicon()
    compact_total = sum(
        token_count(json.dumps(p, sort_keys=True, separators=(",", ":")), specs[0])
        for _, p in messages
    )
    english_total = sum(
        token_count(render_english_lossless(a, p), specs[0]) for a, p in messages
    )
    out: dict[str, dict] = {}
    for enc_name, enc in all_encoders(lex).items():
        lines = encode_transcript(enc, messages)
        sizes = setup_sizes(messages, lines, lex)
        msg_t = token_count("\n".join(lines), specs[0])
        smin = sizes["minimal"]
        cached = cached_setup_cost(smin)
        out[enc_name] = {
            "messages": msg_t,
            "setup_min": smin,
            "total_full": smin + msg_t,
            "total_cached": cached + msg_t,
            "beats_compact_full": smin + msg_t < compact_total,
            "beats_compact_cached": cached + msg_t < compact_total,
            "beats_english_full": smin + msg_t < english_total,
            "beats_english_cached": cached + msg_t < english_total,
        }
    out["_baseline"] = {"compact_json": compact_total, "english_lossless": english_total}
    return out


def format_markdown(results: list[dict], break_even_200: dict, primary: str) -> str:
    lines = [
        "# SYM-3 benchmark",
        "",
        "Decoder setup includes the format header (`sym3/1`), **transcript-minimal lexicon** "
        "(non–self-describing wire tokens only), and **positional schema rows for commands used**. "
        f"**Setup (cached)** = 10% × setup (min); {CACHE_ASSUMPTION}",
        "",
    ]
    for block in results:
        lines.append(f"## {block['transcript']} ({block['count']} messages)")
        lines.append("")
        header = (
            "| Format | setup full | setup min | setup cached† | messages | "
            "total (full setup) | total (cached setup)† | amortized full |"
        )
        sep = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        lines.extend([header, sep])
        for row in block["rows"]:
            sf = row["setup_full"].get(primary, 0)
            sm = row["setup_min"].get(primary, 0)
            sc = row["setup_cached"].get(primary, 0.0)
            msgs = row["messages"].get(primary, 0)
            tf = row["total_full"].get(primary, sf + msgs)
            tc = row["total_cached"].get(primary, sc + msgs)
            amort = tf / block["count"] if block["count"] else 0
            note = row.get("note", "")
            label = row["label"] if not note else f"{row['label']} ({note})"
            lines.append(
                f"| {label} | {sf} | {sm} | {sc:.1f} | {msgs} | {tf} | {tc:.1f} | {amort:.1f} |"
            )
        lines.append("")
        lines.append("† Cached setup assumption (10% of min setup tokens), not API-measured.")
        lines.append("")
        lines.append("### Break-even vs compact JSON / lossless English (setup min, o200k)")
        lines.append("")
        lines.append("| Encoder | msgs to beat compact JSON | msgs to beat English (lossless) |")
        lines.append("| --- | ---: | ---: |")
        for enc, be in sorted(block["break_even"].items()):
            c = be["vs_compact_json"]
            e = be["vs_english_lossless"]
            cs = "never" if c is None else str(c)
            es = "never" if e is None else str(e)
            lines.append(f"| {enc} | {cs} | {es} |")
        lines.append("")

    lines.append("## lifecycle_200 (synthetic, 5× lifecycle_40)")
    lines.append("")
    base = break_even_200["_baseline"]
    lines.append(
        f"Baselines: compact JSON **{base['compact_json']}** tokens; "
        f"English (lossless) **{base['english_lossless']}** tokens (messages only)."
    )
    lines.append("")
    header200 = (
        "| Encoder | setup min | messages | total (full) | total (cached)† | "
        "< compact? (full/cached) | < English lossless? (full/cached) |"
    )
    lines.extend(
        [
            header200,
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for enc in sorted(k for k in break_even_200 if not k.startswith("_")):
        r = break_even_200[enc]
        lines.append(
            f"| {enc} | {r['setup_min']} | {r['messages']} | {r['total_full']} | "
            f"{r['total_cached']:.1f} | {r['beats_compact_full']}/{r['beats_compact_cached']} | "
            f"{r['beats_english_full']}/{r['beats_english_cached']} |"
        )
    lines.append("")
    lines.append("## Verdict (honest accounting, o200k_base)")
    lines.append("")
    lines.append(
        "SYM-3 wire messages are smaller than compact JSON, but a receiver still needs lexicon + schema "
        "context (hundreds of tokens once per session, less when trimmed to the transcript). "
        "On **lifecycle_11**, minimal setup plus messages **does not** beat compact JSON or lossless English "
        "at 11 messages; break-even counts in the tables above show how many messages are needed when "
        "average per-message rates from that transcript are extrapolated linearly. "
        "**refs** / **adaptive** pull ahead on long transcripts with repeated bodies (see lifecycle_40/200), "
        "especially when the cached-prefix pricing assumption applies. "
        "English (lossy summary) is **not** comparable to canonical payloads; use the lossless English row."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    specs = load_tokenizers()
    primary = _primary(specs)
    msgs11 = lifecycle_11()
    msgs40 = lifecycle_40()
    assert len(msgs11) == 11 and len(msgs40) == 40 and len(lifecycle_200()) == 200
    results = [
        run_bench_for_transcript("lifecycle_11", msgs11),
        run_bench_for_transcript("lifecycle_40", msgs40),
    ]
    be200 = run_break_even_200(specs, primary)
    md = format_markdown(results, be200, primary)
    out = __import__("pathlib").Path(__file__).resolve().parents[2] / "docs" / "sym3-bench.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
