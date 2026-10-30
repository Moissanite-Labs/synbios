"""Multi-tokenizer counting utilities for SYM-3 bench and lexicon generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TokenizerSpec:
    name: str
    encode: Callable[[str], list[int]]


def load_tokenizers() -> list[TokenizerSpec]:
    specs: list[TokenizerSpec] = []
    try:
        import tiktoken

        for name in ("o200k_base", "cl100k_base"):
            enc = tiktoken.get_encoding(name)
            specs.append(TokenizerSpec(name, enc.encode))
    except Exception:
        pass

    try:
        from tokenizers import Tokenizer

        for label, model_id in (
            ("qwen2", "Qwen/Qwen2.5-0.5B"),
            ("deepseek", "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"),
        ):
            try:
                tok = Tokenizer.from_pretrained(model_id)
                specs.append(
                    TokenizerSpec(
                        label,
                        lambda text, _t=tok: _t.encode(text, add_special_tokens=False).ids,
                    )
                )
                break
            except Exception:
                continue
    except Exception:
        pass
    return specs


def token_count(text: str, spec: TokenizerSpec) -> int:
    return len(spec.encode(text))


def max_token_count(text: str, specs: list[TokenizerSpec]) -> int:
    if not specs:
        return len(text.split())
    return max(token_count(text, s) for s in specs)


def is_single_token(text: str, specs: list[TokenizerSpec]) -> bool:
    return all(token_count(text, s) == 1 for s in specs)


def pick_cheapest(candidates: list[str], specs: list[TokenizerSpec]) -> tuple[str, int]:
    """Return candidate with lowest max tokenizer count; tie-break shorter string."""
    best = candidates[0]
    best_score = max_token_count(best, specs) if specs else len(best)
    for c in candidates[1:]:
        score = max_token_count(c, specs) if specs else len(c)
        if score < best_score or (score == best_score and len(c) < len(best)):
            best, best_score = c, score
    return best, best_score
