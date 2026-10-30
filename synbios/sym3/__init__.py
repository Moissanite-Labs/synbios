"""SYM-3: token-optimized agent messaging built on lexicon-sized text tokens."""
from __future__ import annotations

from .canonical import ForgeMessage, canonical_payload, normalize_message
from .encoders import (
    ADAPTIVE_TAG,
    COMBINED_TAG,
    DELTA_TAG,
    OMIT_TAG,
    POSITIONAL_TAG,
    REFS_TAG,
    AdaptiveEncoder,
    CombinedEncoder,
    DeltaEncoder,
    OmitEncoder,
    PositionalEncoder,
    RefsEncoder,
    all_encoders,
)
from .lexicon import Lexicon, load_lexicon

__all__ = [
    "ForgeMessage",
    "canonical_payload",
    "normalize_message",
    "Lexicon",
    "load_lexicon",
    "DeltaEncoder",
    "RefsEncoder",
    "PositionalEncoder",
    "OmitEncoder",
    "CombinedEncoder",
    "AdaptiveEncoder",
    "all_encoders",
    "DELTA_TAG",
    "REFS_TAG",
    "POSITIONAL_TAG",
    "OMIT_TAG",
    "COMBINED_TAG",
    "ADAPTIVE_TAG",
]
