"""SYM-3 wire encoders and decoders."""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from synbios.store import COMMAND_FIELDS

from .canonical import ForgeMessage, canonical_payload, normalize_message
from .content_store import ContentStore
from .lexicon import Lexicon, load_lexicon
from .schema import POSITIONAL_ORDER
from .state import Sym3Session

_QUOTED = re.compile(r'"((?:\\.|[^"\\])*)"')


def _quote(s: str) -> str:
    esc = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def _escape_token(value: Any, session: Sym3Session, content: ContentStore, use_refs: bool) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if use_refs:
            return _escape_token(session.content.ref_if_published(value), session, content, False)
        return _quote(blob)
    if isinstance(value, str):
        if use_refs:
            published = session.content.ref_if_published(value)
            if isinstance(published, str) and published != value and published in session.content.ref_to_digest:
                return published
            value = published if isinstance(published, str) else value
        if value in {"p", "t", "a", "h", "f"}:
            return value
        if value == session.project_id:
            return "p"
        if value == session.task_id:
            return "t"
        if value == session.agent_id:
            return "a"
        if value == session.human_id:
            return "h"
        if value == session.artifact_id:
            return "f"
        if " " in value or ";" in value or "," in value or '"' in value or value.startswith("http"):
            return _quote(value)
        return value
    return _quote(str(value))


def _split_line(line: str) -> list[str]:
    parts: list[str] = []
    i = 0
    while i < len(line):
        if line[i] == '"':
            m = _QUOTED.match(line, i)
            if not m:
                raise ValueError("bad quoted token")
            parts.append(m.group(1).replace('\\"', '"').replace("\\\\", "\\"))
            i = m.end()
            continue
        j = i
        while j < len(line) and line[j] not in " ":
            j += 1
        parts.append(line[i:j])
        i = j + 1 if j < len(line) and line[j] == " " else j
    return [p for p in parts if p != ""]


def _unescape_token(token: str, session: Sym3Session, content: ContentStore) -> Any:
    if token == "-":
        return None
    if token in session.content.ref_to_digest:
        return session.content.resolve(token)
    if token in {"p", "t", "a", "h", "f"}:
        _, rid = session.resolve_ref(token)
        return rid
    if token.startswith("[") or token.startswith("{"):
        try:
            val = json.loads(token)
            session.content.observe_inline(val)
            return val
        except json.JSONDecodeError:
            pass
    if token.isdigit():
        return int(token)
    session.content.observe_inline(token)
    return token


def _cmd_from_lex(lex: Lexicon, word: str) -> str:
    word_stripped = word.strip()
    matches = [cmd for cmd, w in lex.raw["cmd"].items() if w.strip() == word_stripped or w == word]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous command lexeme {word!r}")
    raise ValueError(f"unknown command lexeme {word!r}")


def _lex_cmd(lex: Lexicon, action: str) -> str:
    return lex.word("cmd", action).strip()


class Encoder(ABC):
    tag_name: str

    def __init__(self, lexicon: Lexicon | None = None) -> None:
        self.lex = lexicon or load_lexicon()

    @property
    def tag(self) -> str:
        return self.lex.tag(self.tag_name)

    @abstractmethod
    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str: ...

    @abstractmethod
    def decode(self, line: str, session: Sym3Session) -> ForgeMessage: ...


class PositionalEncoder(Encoder):
    tag_name = "positional"

    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str:
        full = canonical_payload(action, payload)
        order = POSITIONAL_ORDER[action]
        vals = [_escape_token(full[k], session, session.content, use_refs=False) for k in order]
        return f"{self.tag}{_lex_cmd(self.lex, action)} {' '.join(vals)}"

    def decode(self, line: str, session: Sym3Session) -> ForgeMessage:
        body = line[len(self.tag) :] if line.startswith(self.tag) else line
        parts = _split_line(body.strip())
        action = _cmd_from_lex(self.lex, parts[0])
        order = POSITIONAL_ORDER[action]
        payload: dict[str, Any] = {}
        for key, tok in zip(order, parts[1:]):
            payload[key] = _unescape_token(tok, session, session.content)
        return normalize_message(action, payload)


class OmitEncoder(Encoder):
    tag_name = "omit"

    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str:
        sparse = session.omit_defaults(action, payload)
        order = [k for k in POSITIONAL_ORDER[action] if k in sparse]
        vals = [_escape_token(sparse[k], session, session.content, use_refs=False) for k in order]
        keys_blob = "|".join(order) + "|"
        return f"{self.tag}{_lex_cmd(self.lex, action)} {keys_blob} {' '.join(vals)}"

    def decode(self, line: str, session: Sym3Session) -> ForgeMessage:
        body = line[len(self.tag) :].strip()
        parts = _split_line(body)
        action = _cmd_from_lex(self.lex, parts[0])
        if len(parts) > 2 and parts[1].endswith("|"):
            keys = parts[1][:-1].split("|") if parts[1][:-1] else []
            vals = parts[2:]
        else:
            keys = POSITIONAL_ORDER[action]
            vals = parts[1:]
        payload: dict[str, Any] = {}
        for key, tok in zip(keys, vals):
            payload[key] = _unescape_token(tok, session, session.content)
        return normalize_message(action, session.restore_defaults(action, payload))


class RefsEncoder(Encoder):
    tag_name = "refs"

    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str:
        full = canonical_payload(action, payload)
        order = POSITIONAL_ORDER[action]
        vals = [_escape_token(full[k], session, session.content, use_refs=True) for k in order]
        return f"{self.tag}{_lex_cmd(self.lex, action)} {' '.join(vals)}"

    def decode(self, line: str, session: Sym3Session) -> ForgeMessage:
        body = line[len(self.tag) :].strip()
        parts = _split_line(body)
        action = _cmd_from_lex(self.lex, parts[0])
        order = POSITIONAL_ORDER[action]
        payload: dict[str, Any] = {}
        for key, tok in zip(order, parts[1:]):
            val = _unescape_token(tok, session, session.content)
            if isinstance(val, str) and val in session.content.ref_to_digest:
                val = session.content.resolve(val)
            payload[key] = val
        return normalize_message(action, payload)


class DeltaEncoder(Encoder):
    tag_name = "delta"

    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str:
        delta = session.delta_payload(action, payload)
        if delta and action == "task.transition":
            st_word = self.lex.word("status", delta["status"]).strip()
            return f"{self.tag}{_lex_cmd(self.lex, action)} t st={st_word}"
        omit = OmitEncoder(self.lex)
        line = omit.encode(action, payload, session)
        return line.replace(omit.tag, self.tag, 1)

    def decode(self, line: str, session: Sym3Session) -> ForgeMessage:
        body = line[len(self.tag) :].strip()
        parts = _split_line(body)
        action = _cmd_from_lex(self.lex, parts[0])
        if len(parts) >= 3 and parts[2].startswith("st="):
            st_word = parts[2][3:]
            status = _status_from_lex(self.lex, st_word)
            return normalize_message(action, {"task_id": session.task_id, "status": status})
        omit = OmitEncoder(self.lex)
        return omit.decode(omit.tag + body, session)


def _status_from_lex(lex: Lexicon, word: str) -> str:
    for st, w in lex.raw["status"].items():
        if w.strip() == word.strip():
            return st
    return word


class CombinedEncoder(Encoder):
    tag_name = "combined"

    def __init__(self, lexicon: Lexicon | None = None) -> None:
        super().__init__(lexicon)
        self._delta = DeltaEncoder(self.lex)
        self._refs = RefsEncoder(self.lex)

    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str:
        delta = session.delta_payload(action, payload)
        if delta and action == "task.transition":
            line = self._delta.encode(action, payload, session)
            return line.replace(self._delta.tag, self.tag, 1)
        sparse = session.omit_defaults(action, payload)
        order = [k for k in POSITIONAL_ORDER[action] if k in sparse]
        vals = [_escape_token(sparse[k], session, session.content, use_refs=True) for k in order]
        keys_blob = "|".join(order) + "|"
        return f"{self.tag}{_lex_cmd(self.lex, action)} {keys_blob} {' '.join(vals)}"

    def decode(self, line: str, session: Sym3Session) -> ForgeMessage:
        if " st=" in line:
            return self._delta.decode(line.replace(self.tag, self._delta.tag, 1), session)
        body = line[len(self.tag) :].strip()
        parts = _split_line(body)
        action = _cmd_from_lex(self.lex, parts[0])
        if len(parts) > 2 and parts[1].endswith("|"):
            keys = parts[1][:-1].split("|") if parts[1][:-1] else []
            vals = parts[2:]
            payload: dict[str, Any] = {}
            for key, tok in zip(keys, vals):
                val = _unescape_token(tok, session, session.content)
                if isinstance(val, str) and val in session.content.ref_to_digest:
                    val = session.content.resolve(val)
                payload[key] = val
            return normalize_message(action, session.restore_defaults(action, payload))
        return self._refs.decode(line.replace(self.tag, self._refs.tag, 1), session)


@dataclass
class AdaptiveResult:
    line: str
    encoder: str
    encode_cpu_ns: int


class AdaptiveEncoder(Encoder):
    tag_name = "adaptive"

    def __init__(self, lexicon: Lexicon | None = None) -> None:
        super().__init__(lexicon)
        self._choices = [
            DeltaEncoder(self.lex),
            RefsEncoder(self.lex),
            OmitEncoder(self.lex),
            PositionalEncoder(self.lex),
            CombinedEncoder(self.lex),
        ]

    def encode(self, action: str, payload: dict[str, Any], session: Sym3Session) -> str:
        return self.encode_adaptive(action, payload, session).line

    def encode_adaptive(self, action: str, payload: dict[str, Any], session: Sym3Session) -> AdaptiveResult:
        from .tokens import load_tokenizers, max_token_count

        specs = load_tokenizers()
        best_line = ""
        best_name = ""
        best_score = 10**9
        best_ns = 0
        for enc in self._choices:
            t0 = time.perf_counter_ns()
            line = enc.encode(action, payload, session)
            ns = time.perf_counter_ns() - t0
            score = max_token_count(line, specs) if specs else len(line)
            if score < best_score:
                best_score = score
                best_line = line
                best_name = enc.tag_name
                best_ns = ns
        tag = self.lex.tag("adaptive")
        inner_tag = self.lex.tag(best_name)
        wrapped = best_line.replace(inner_tag, tag, 1) if best_line.startswith(inner_tag) else f"{tag}{best_line}"
        return AdaptiveResult(wrapped, best_name, best_ns)

    def decode(self, line: str, session: Sym3Session) -> ForgeMessage:
        if not line.startswith(self.tag):
            raise ValueError("not an adaptive line")
        for name in ("delta", "combined", "refs", "omit", "positional"):
            candidate = line.replace(self.tag, self.lex.tag(name), 1)
            try:
                return _encoder_by_name(name, self.lex).decode(candidate, session)
            except Exception:
                continue
        raise ValueError("cannot decode adaptive line")


def _encoder_by_name(name: str, lex: Lexicon) -> Encoder:
    return {
        "delta": DeltaEncoder(lex),
        "refs": RefsEncoder(lex),
        "omit": OmitEncoder(lex),
        "positional": PositionalEncoder(lex),
        "combined": CombinedEncoder(lex),
    }[name]


DELTA_TAG = "delta"
REFS_TAG = "refs"
POSITIONAL_TAG = "positional"
OMIT_TAG = "omit"
COMBINED_TAG = "combined"
ADAPTIVE_TAG = "adaptive"


def all_encoders(lex: Lexicon | None = None) -> dict[str, Encoder]:
    lex = lex or load_lexicon()
    return {
        DELTA_TAG: DeltaEncoder(lex),
        REFS_TAG: RefsEncoder(lex),
        POSITIONAL_TAG: PositionalEncoder(lex),
        OMIT_TAG: OmitEncoder(lex),
        COMBINED_TAG: CombinedEncoder(lex),
        ADAPTIVE_TAG: AdaptiveEncoder(lex),
    }


def fresh_session() -> Sym3Session:
    """Session ids aligned with synbios/sym2p bench lifecycle fixtures."""
    session = Sym3Session()
    session.project_id = "a1" * 16
    session.task_id = "b2" * 16
    session.agent_id = "c3" * 16
    session.human_id = "d4" * 16
    session.artifact_id = "e5" * 16
    return session


def encode_transcript(encoder: Encoder, messages: list[ForgeMessage]) -> list[str]:
    session = fresh_session()
    lines: list[str] = []
    for action, payload in messages:
        lines.append(encoder.encode(action, payload, session))
        session.apply_message(action, payload)
    return lines


def decode_transcript(encoder: Encoder, lines: list[str]) -> list[ForgeMessage]:
    session = fresh_session()
    out: list[ForgeMessage] = []
    for line in lines:
        msg = encoder.decode(line, session)
        out.append(msg)
        session.apply_message(msg[0], msg[1])
    return out


def setup_prefix(lex: Lexicon | None = None) -> str:
    lex = lex or load_lexicon()
    return "sym3/1\n"
