#!/usr/bin/env python3
"""Optional LLM comprehension check for SYM-3 wire lines (skipped in CI without API key)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from .encoders import all_encoders, decode_transcript, encode_transcript
from .fixtures import lifecycle_11


PROMPT = """Decode each SYM-3 line to JSON objects with keys "cmd" and "payload".
Return a JSON array only, one object per input line, same order."""


def _openai_chat(api_key: str, model: str, user: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def score_predictions(expected: list[dict], predicted: list[dict]) -> float:
    if len(expected) != len(predicted):
        return 0.0
    ok = 0
    for exp, got in zip(expected, predicted):
        if exp == got:
            ok += 1
    return ok / len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description="SYM-3 comprehension harness")
    parser.add_argument("--encoder", default="combined")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set; comprehension check skipped")
        return 0
    enc = all_encoders()[args.encoder]
    messages = lifecycle_11()
    lines = encode_transcript(enc, messages)
    expected = [{"cmd": a, "payload": p} for a, p in messages]
    user_blob = "\n".join(lines)
    try:
        raw = _openai_chat(api_key, args.model, user_blob)
    except urllib.error.URLError as exc:
        print(f"API call failed: {exc}")
        return 1
    predicted = json.loads(raw)
    acc = score_predictions(expected, predicted)
    print(f"field-exact accuracy: {acc * 100:.1f}%")
    return 0 if acc >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(main())
