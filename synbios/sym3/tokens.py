"""Multi-tokenizer counting utilities for SYM-3 bench and lexicon generation."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

# Pinned via requirements-bench.txt, primary first. The committed lexicon and
# docs/sym3-bench.md were generated with exactly this set.
BENCH_TOKENIZERS = ("o200k_base", "cl100k_base")
# Extra tokenizers change adaptive choices, ref labels and the lexicon, so
# they load only on request.
EXTRA_TOKENIZERS_ENV = "SYM3_EXTRA_TOKENIZERS"


class TokenizerUnavailable(RuntimeError):
    """The pinned bench tokenizers could not be loaded."""


@dataclass(frozen=True)
class TokenizerSpec:
    name: str
    encode: Callable[[str], list[int]]


def _extra_requested() -> bool:
    return os.environ.get(EXTRA_TOKENIZERS_ENV) == "1"


@lru_cache(maxsize=None)
def _load(include_extra: bool) -> tuple[tuple[TokenizerSpec, ...], str | None]:
    specs: list[TokenizerSpec] = []
    error = None
    try:
        import tiktoken

        for name in BENCH_TOKENIZERS:
            enc = tiktoken.get_encoding(name)
            specs.append(TokenizerSpec(name, enc.encode))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if include_extra:
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
    return tuple(specs), error


def load_tokenizers() -> list[TokenizerSpec]:
    """Loadable tokenizers, primary first; empty if tiktoken cannot load. Cached per process."""
    specs, _error = _load(_extra_requested())
    return list(specs)


def require_bench_tokenizers() -> list[TokenizerSpec]:
    """Exactly the pinned bench tokenizers, or TokenizerUnavailable naming the cause."""
    include_extra = _extra_requested()
    specs, error = _load(include_extra)
    names = tuple(s.name for s in specs)
    if names == BENCH_TOKENIZERS:
        return list(specs)
    if include_extra:
        cause = f"Unset {EXTRA_TOKENIZERS_ENV}; extra tokenizers change bench results."
    elif error and error.startswith("ModuleNotFoundError"):
        cause = "tiktoken is not installed; run: pip install -r requirements-bench.txt"
    else:
        cause = (
            f"tiktoken failed ({error}). tiktoken downloads encodings on first use; allow that "
            "download or set TIKTOKEN_CACHE_DIR to a cache that already holds them."
        )
    raise TokenizerUnavailable(
        f"SYM-3 bench requires tokenizers {', '.join(BENCH_TOKENIZERS)}; "
        f"loaded: {', '.join(names) or 'none'}. {cause}"
    )


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
