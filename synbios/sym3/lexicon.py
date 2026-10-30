"""Load committed SYM-3 lexicon."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parent / "lexicon.json"


@dataclass(frozen=True)
class Lexicon:
    raw: dict[str, dict[str, str]]
    format_tags: dict[str, str]

    def word(self, category: str, concept: str) -> str:
        block = self.raw.get(category) or {}
        if concept not in block:
            raise KeyError(f"lexicon missing {category}.{concept}")
        return block[concept]

    def tag(self, name: str) -> str:
        return self.format_tags[name]


@lru_cache(maxsize=1)
def load_lexicon(path: Path | None = None) -> Lexicon:
    data = json.loads((path or LEXICON_PATH).read_text(encoding="utf-8"))
    return Lexicon(raw=data["concepts"], format_tags=data["format_tags"])
