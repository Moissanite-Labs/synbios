"""Content-addressed store with tokenizer-cheap ref labels."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .tokens import load_tokenizers, pick_cheapest


def _canonical_bytes(value: str | list | dict) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_digest(value: str | list | dict) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()[:16]


@dataclass
class ContentStore:
    by_digest: dict[str, str | list | dict] = field(default_factory=dict)
    digest_to_ref: dict[str, str] = field(default_factory=dict)
    ref_to_digest: dict[str, str] = field(default_factory=dict)
    published_on_wire: set[str] = field(default_factory=set)
    _seq: int = 0

    def intern(self, value: str | list | dict, *, min_len: int = 48) -> str | list | dict:
        raw = value
        serialized = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(serialized) < min_len:
            return value
        dg = content_digest(value)
        self.by_digest[dg] = raw
        if dg in self.digest_to_ref:
            ref = self.digest_to_ref[dg]
            if dg in self.published_on_wire:
                return ref
            return raw
        ref = self._alloc_ref(dg)
        self.digest_to_ref[dg] = ref
        self.ref_to_digest[ref] = dg
        return raw

    def ref_if_published(self, value: str | list | dict) -> str | list | dict:
        """After first inline publish, emit cheap ref token."""
        serialized = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(serialized) < 48:
            return value
        dg = content_digest(value)
        if dg not in self.by_digest:
            self.by_digest[dg] = value
        if dg not in self.digest_to_ref:
            ref = self._alloc_ref(dg)
            self.digest_to_ref[dg] = ref
            self.ref_to_digest[ref] = dg
        if dg in self.published_on_wire:
            return self.digest_to_ref[dg]
        self.published_on_wire.add(dg)
        return value

    def mark_from_wire(self, token: str, value: str | list | dict) -> None:
        dg = content_digest(value)
        self.by_digest[dg] = value
        if token not in self.ref_to_digest:
            self.ref_to_digest[token] = dg
            self.digest_to_ref[dg] = token
        self.published_on_wire.add(dg)

    def resolve(self, token: str) -> str | list | dict:
        if token in self.ref_to_digest:
            dg = self.ref_to_digest[token]
            return self.by_digest[dg]
        raise KeyError(f"unknown content ref {token!r}")

    def observe_inline(self, value: str | list | dict) -> None:
        serialized = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
        if len(serialized) < 48:
            return
        dg = content_digest(value)
        self.by_digest[dg] = value
        if dg not in self.digest_to_ref:
            ref = self._alloc_ref(dg)
            self.digest_to_ref[dg] = ref
            self.ref_to_digest[ref] = dg
        self.published_on_wire.add(dg)

    def _alloc_ref(self, digest: str) -> str:
        from .tokens import is_single_token

        specs = load_tokenizers()
        candidates: list[str] = []
        for i in range(1, 512):
            for prefix in ("#", " r", " x", " z"):
                candidates.append(f"{prefix}{i}")
        singles = [c for c in candidates if specs and is_single_token(c, specs)]
        pool = singles or candidates
        for _ in range(3):
            best, _ = pick_cheapest(pool, specs)
            if best not in self.ref_to_digest:
                return best
            pool = [c for c in pool if c != best]
        self._seq += 1
        return f"#h{self._seq:x}"
