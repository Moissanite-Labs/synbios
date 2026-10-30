"""Decoder context sizing: full vs transcript-minimal lexicon and schema."""
from __future__ import annotations

import json
from typing import Any

from synbios.store import COMMAND_FIELDS

from .canonical import canonical_payload
from .lexicon import LEXICON_PATH, Lexicon, load_lexicon
from .schema import POSITIONAL_ORDER

FORMAT_HEADER = "sym3/1\n"


def full_positional_schema() -> dict[str, list[str]]:
    return {k: list(v) for k, v in POSITIONAL_ORDER.items()}


def _collect_used_from_transcript(
    messages: list[tuple[str, dict]],
    encoded_lines: list[str],
    lex: Lexicon,
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Return used cmd actions, status values, kind values, format tag names."""
    cmds = {a for a, _ in messages}
    statuses: set[str] = set()
    kinds: set[str] = set()
    for action, payload in messages:
        full = canonical_payload(action, payload)
        if "status" in full:
            statuses.add(full["status"])
        if "kind" in full:
            kinds.add(full["kind"])
        if "decision" in full:
            kinds.add(full["decision"])
        if "priority" in full:
            kinds.add(full["priority"])
    tag_names: set[str] = set()
    all_tags = {v: k for k, v in lex.format_tags.items()}
    for line in encoded_lines:
        for tag, name in all_tags.items():
            if line.startswith(tag):
                tag_names.add(name)
                break
    if "adaptive" in tag_names:
        tag_names = set(lex.format_tags.keys())
    return cmds, statuses, kinds, tag_names


def _minimal_lexicon_payload(
    lex: Lexicon,
    cmds: set[str],
    statuses: set[str],
    kinds: set[str],
    tag_names: set[str],
) -> dict[str, Any]:
    """Decode-sufficient lexicon: every used cmd/status/kind wire mapping + format tags."""
    out: dict[str, Any] = {"concepts": {}, "format_tags": {}}
    for cat, used in (
        ("cmd", cmds),
        ("status", statuses),
        ("kind", kinds),
    ):
        block = lex.raw.get(cat) or {}
        for concept in sorted(used):
            if concept not in block:
                continue
            out["concepts"].setdefault(cat, {})[concept] = block[concept]
    for name in sorted(tag_names):
        out["format_tags"][name] = lex.format_tags[name]
    return out


def parse_decoder_context(text: str) -> tuple[Lexicon, dict[str, list[str]]]:
    """Parse rendered decoder context into Lexicon + schema (fresh, no committed file)."""
    lines = text.strip().split("\n")
    if not lines or not lines[0].startswith("sym3/"):
        raise ValueError("missing sym3 format header")
    lex_payload: dict[str, Any] = {"concepts": {}, "format_tags": {}}
    schema: dict[str, list[str]] = {}
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line == "lexicon:":
            i += 1
            lex_payload = json.loads(lines[i])
            i += 1
            continue
        if line == "schema:":
            i += 1
            schema = json.loads(lines[i])
            i += 1
            continue
        i += 1
    concepts = lex_payload.get("concepts") or {}
    format_tags = lex_payload.get("format_tags") or {}
    return Lexicon(raw=concepts, format_tags=format_tags), schema


def _minimal_schema(cmds: set[str]) -> dict[str, list[str]]:
    return {c: list(POSITIONAL_ORDER[c]) for c in sorted(cmds) if c in POSITIONAL_ORDER}


def render_decoder_context(
    *,
    lexicon_payload: dict[str, Any] | None,
    schema: dict[str, list[str]],
    include_full_lexicon_file: bool = False,
) -> str:
    parts = [FORMAT_HEADER.rstrip(), ""]
    if include_full_lexicon_file:
        parts.append("lexicon:")
        parts.append(LEXICON_PATH.read_text(encoding="utf-8").strip())
    elif lexicon_payload is not None:
        parts.append("lexicon:")
        parts.append(json.dumps(lexicon_payload, sort_keys=True, separators=(",", ":")))
    parts.append("schema:")
    parts.append(json.dumps(schema, sort_keys=True, separators=(",", ":")))
    return "\n".join(parts) + "\n"


def setup_sizes(
    messages: list[tuple[str, dict]],
    encoded_lines: list[str],
    lex: Lexicon | None = None,
) -> dict[str, int]:
    from .tokens import load_tokenizers, token_count

    lex = lex or load_lexicon()
    specs = load_tokenizers()
    primary = specs[0] if specs else None

    def count(text: str) -> int:
        if not primary:
            return len(text.split())
        return token_count(text, primary)

    full_lex = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    full_schema = full_positional_schema()
    full_text = render_decoder_context(
        lexicon_payload=full_lex,
        schema=full_schema,
        include_full_lexicon_file=False,
    )
    cmds, statuses, kinds, tag_names = _collect_used_from_transcript(messages, encoded_lines, lex)
    minimal_lex = _minimal_lexicon_payload(lex, cmds, statuses, kinds, tag_names)
    minimal_schema = _minimal_schema(cmds)
    minimal_text = render_decoder_context(lexicon_payload=minimal_lex, schema=minimal_schema)
    header_only = FORMAT_HEADER
    return {
        "header_only": count(header_only),
        "minimal": count(minimal_text),
        "full": count(full_text),
        "minimal_text": minimal_text,
        "full_text": full_text,
    }


def cached_setup_cost(setup_tokens: int, *, discount: float = 0.1) -> float:
    """Assumed cached prompt-prefix cost (one-time, discounted)."""
    return setup_tokens * discount
