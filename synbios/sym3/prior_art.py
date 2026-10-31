"""Prior-art and alternative wire baselines for SYM-3 bench."""
from __future__ import annotations

import hashlib
import json

from .canonical import canonical_payload

# Agora (multi-agent messaging); arXiv:2410.11905 — cited as prior art for SYM-3 refs.
AGORA_ARXIV = "2410.11905"
AGORA_SPEC = (
    "Agora-style deterministic envelope: one line per message, "
    "SHA-256 of this spec document, space, compact JSON object with cmd and payload."
)
AGORA_SPEC_SHA256 = hashlib.sha256(AGORA_SPEC.encode()).hexdigest()
AGORA_PREFIX = f"agora/{AGORA_ARXIV}/{AGORA_SPEC_SHA256[:16]}"


def _canonical_message(action: str, payload: dict) -> dict:
    return {"cmd": action, "payload": canonical_payload(action, payload)}


def encode_toon_line(action: str, payload: dict) -> str:
    try:
        import toon_format as toon

        return toon.dumps(_canonical_message(action, payload)).strip()
    except ImportError:
        return _toon_fallback(action, payload)


def _toon_fallback(action: str, payload: dict) -> str:
    """Minimal TOON-like encoding when toon-format is not installed (see github.com/toon-format/toon)."""
    msg = _canonical_message(action, payload)
    lines = [f"cmd: {msg['cmd']}", "payload:"]
    for key, value in sorted(msg["payload"].items()):
        if isinstance(value, list):
            lines.append(f"  {key}[{len(value)}]: {','.join(json.dumps(v) for v in value)}")
        else:
            lines.append(f"  {key}: {json.dumps(value) if isinstance(value, (dict, list)) else value}")
    return "\n".join(lines)


def encode_key_value_line(action: str, payload: dict) -> str:
    """Lossless key=value text: command words, then every canonical field as key=value."""
    p = canonical_payload(action, payload)
    parts = [action.replace(".", " ")]
    for key in sorted(p.keys()):
        val = p[key]
        if isinstance(val, list):
            parts.append(f"{key}={';'.join(json.dumps(v, separators=(',', ':')) for v in val)}")
        else:
            parts.append(f"{key}={json.dumps(val, separators=(',', ':')) if isinstance(val, str) else val}")
    return " ".join(parts)


def encode_agora_line(action: str, payload: dict) -> str:
    body = json.dumps(_canonical_message(action, payload), sort_keys=True, separators=(",", ":"))
    return f"{AGORA_PREFIX} {body}"


def agora_setup_prefix() -> str:
    return f"{AGORA_SPEC}\n{AGORA_PREFIX}\n"
