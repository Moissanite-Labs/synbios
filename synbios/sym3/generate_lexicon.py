#!/usr/bin/env python3
"""Regenerate synbios/sym3/lexicon.json from tokenizer-aware candidate search."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from synbios.store import COMMAND_FIELDS

from .tokens import is_single_token, load_tokenizers, max_token_count, pick_cheapest

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "lexicon.json"

# Leading-space variants matter for mid-line tokens; bare variants for line starts.
SPACE_PREFIXES = ("", " ")


def _candidates(base: str, extras: list[str] | None = None) -> list[str]:
    words = [base]
    if extras:
        words.extend(extras)
    # Short aliases and abbreviations
    aliases = {
        "project": ["proj", "prj"],
        "principal": ["actor", "who"],
        "grant": ["perm", "cap"],
        "task": ["job", "work"],
        "artifact": ["art", "file"],
        "evidence": ["proof", "test"],
        "review": ["rev", "sign"],
        "create": ["add", "new", "mk", "open"],
        "claim": ["take", "own"],
        "transition": ["move", "set", "go"],
        "description": ["desc", "about"],
        "repository": ["repo", "git"],
        "capabilities": ["caps", "perms"],
        "dependencies": ["deps", "needs"],
        "priority": ["pri", "rank"],
        "in_progress": ["doing", "run", "active"],
        "in_review": ["reviewing", "check"],
        "approved": ["ok", "yes", "pass"],
        "changes_requested": ["fix", "no", "redo"],
        "git_commit": ["commit", "git"],
        "passed": ["ok", "pass", "green"],
        "agent": ["bot", "ai"],
        "human": ["person", "user"],
        "high": ["urgent", "p1"],
        "normal": ["std", "p2"],
    }
    for key, al in aliases.items():
        if key in base:
            words.extend(al)
    out: list[str] = []
    for w in sorted(set(words)):
        for p in SPACE_PREFIXES:
            out.append(f"{p}{w}")
    return out


def _build_concepts() -> dict[str, dict[str, list[str]]]:
    concepts: dict[str, dict[str, list[str]]] = {
        "cmd": {},
        "field": {},
        "status": {},
        "kind": {},
        "misc": {},
    }
    for cmd in sorted(COMMAND_FIELDS):
        concepts["cmd"][cmd] = _cmd_candidates(cmd)
    for _action, fields in COMMAND_FIELDS.items():
        for f in sorted(fields):
            concepts["field"].setdefault(f, _candidates(f))
    for st in (
        "open",
        "in_progress",
        "in_review",
        "cancelled",
        "accepted",
        "proposed",
        "verified",
        "disputed",
        "rejected",
        "observed",
        "assumed",
        "inferred",
        "passed",
        "failed",
    ):
        concepts["status"][st] = _candidates(st, [st.replace("_", "")])
    for k in ("agent", "human", "git_commit", "document", "test", "high", "normal", "approved", "changes_requested"):
        concepts["kind"][k] = _candidates(k)
    concepts["misc"]["true"] = ["1", "yes", "y", "on"]
    concepts["misc"]["false"] = ["0", "no", "n", "off"]
    concepts["misc"]["list_sep"] = [";", "|", ","]
    concepts["misc"]["ref_prefix"] = ["#", "@", "$", "r"]
    return concepts


def _cmd_candidates(cmd: str) -> list[str]:
    verb, noun = cmd.split(".", 1)
    extras = [
        cmd.replace(".", ""),
        f"{verb[:1]}{noun[:3]}",
        f"{verb[:2]}{noun[:2]}",
        f"{noun[:1]}{verb[:2]}",
        noun,
        verb,
        cmd.replace(".", "_"),
    ]
    return _candidates(cmd.replace(".", " "), extras)


def _pick_unique(concepts: dict[str, list[str]], specs) -> dict[str, str]:
    used: set[str] = set()
    out: dict[str, str] = {}
    for concept in sorted(concepts):
        cands = concepts[concept]
        singles = [c for c in cands if is_single_token(c, specs)]
        pool = singles if singles else cands

        def rank_key(c: str) -> tuple:
            stripped = c.strip()
            natural = stripped == concept or stripped == concept.replace("_", "") or stripped == concept.split(".")[-1]
            return (0 if natural else 1, max_token_count(c, specs), len(c))

        ranked = sorted(pool, key=rank_key)
        chosen = None
        for c in ranked:
            key = c.strip()
            if key not in used:
                chosen = c
                used.add(key)
                break
        if chosen is None:
            # suffix disambiguation
            base = ranked[0]
            for n in range(2, 100):
                alt = f"{base}{n}"
                if is_single_token(alt, specs) and alt.strip() not in used:
                    chosen = alt
                    used.add(alt.strip())
                    break
        if chosen is None:
            chosen = ranked[0]
            used.add(chosen.strip())
        out[concept] = chosen
    return out


def _format_tag_candidates() -> dict[str, list[str]]:
    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    tags = {
        "delta": letters[0:4],
        "refs": letters[4:8],
        "positional": letters[8:12],
        "omit": letters[12:16],
        "combined": letters[16:20],
        "adaptive": letters[20:24],
    }
    return tags


def main() -> int:
    specs = load_tokenizers()
    if not specs:
        print("No tokenizers available; install tiktoken", file=sys.stderr)
        return 1
    concepts_in = _build_concepts()
    chosen: dict[str, dict[str, str]] = {}
    for category, mapping in concepts_in.items():
        if category == "cmd":
            chosen[category] = _pick_unique(mapping, specs)
        else:
            chosen[category] = {}
            for concept, cands in sorted(mapping.items()):
                singles = [c for c in cands if is_single_token(c, specs)]
                pool = singles if singles else cands

                def rank_key(c: str, _concept=concept) -> tuple:
                    stripped = c.strip()
                    natural = stripped == _concept or stripped == _concept.replace("_", "")
                    return (0 if natural else 1, max_token_count(c, specs), len(c))

                word = sorted(pool, key=rank_key)[0]
                chosen[category][concept] = word

    format_tags: dict[str, str] = {}
    used_tags: set[str] = set()
    for name, cands in _format_tag_candidates().items():
        singles = [c for c in cands if is_single_token(c, specs)]
        pool = singles if singles else cands
        ranked = sorted(pool, key=lambda c: (max_token_count(c, specs), len(c)))
        pick = None
        for c in ranked:
            if c.strip() not in used_tags:
                pick = c
                used_tags.add(c.strip())
                break
        if pick is None:
            pick, _ = pick_cheapest(pool, specs)
        format_tags[name] = pick

    payload = {
        "version": 1,
        "tokenizers": [s.name for s in specs],
        "concepts": chosen,
        "format_tags": format_tags,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(specs)} tokenizers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
