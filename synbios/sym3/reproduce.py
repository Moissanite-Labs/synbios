#!/usr/bin/env python3
"""Regenerate SYM-3 benchmark tables, write results JSON, verify committed numbers."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .bench import format_markdown, run_bench_for_transcript
from .fixtures import lifecycle_11, lifecycle_40, lifecycle_200
from .tokens import load_tokenizers

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_MD = REPO_ROOT / "docs" / "sym3-bench.md"
RESULTS_JSON = REPO_ROOT / "docs" / "paper" / "sym3-bench-results.json"
REQUIREMENTS_BENCH = REPO_ROOT / "requirements-bench.txt"


def _git_sha(full: bool = True) -> str:
    try:
        if full:
            cmd = ["git", "rev-parse", "HEAD"]
        else:
            cmd = ["git", "rev-parse", "--short=7", "HEAD"]
        out = subprocess.check_output(cmd, cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _bench_dependency_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    if REQUIREMENTS_BENCH.is_file():
        for line in REQUIREMENTS_BENCH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "==" in line:
                name, ver = line.split("==", 1)
                pins[name.strip()] = ver.strip()
    return pins


def _tokenizer_metadata() -> dict:
    specs = load_tokenizers()
    pins = _bench_dependency_pins()
    meta: dict = {
        "primary": specs[0].name if specs else None,
        "encodings": [s.name for s in specs],
        "dependency_pins": pins,
    }
    try:
        import tiktoken

        meta["tiktoken_version"] = tiktoken.__version__
    except Exception:
        meta["tiktoken_version"] = None
    return meta


def run_all_benches() -> tuple[list[dict], str, str]:
    specs = load_tokenizers()
    primary = specs[0].name if specs else "n/a"
    assert len(lifecycle_11()) == 11
    assert len(lifecycle_40()) == 40
    assert len(lifecycle_200()) == 200
    results = [
        run_bench_for_transcript("lifecycle_11", lifecycle_11()),
        run_bench_for_transcript("lifecycle_40", lifecycle_40()),
        run_bench_for_transcript("lifecycle_200", lifecycle_200()),
    ]
    md = format_markdown(results, primary)
    return results, md, primary


def _normalize_md(text: str) -> str:
    return text.replace("\r\n", "\n").strip() + "\n"


def verify_against_committed(generated_md: str) -> None:
    if not BENCH_MD.is_file():
        raise SystemExit(f"Missing committed benchmark: {BENCH_MD}")
    committed = _normalize_md(BENCH_MD.read_text(encoding="utf-8"))
    generated = _normalize_md(generated_md)
    if committed != generated:
        diff_hint = "Re-run with --write-md after intentional bench changes."
        raise SystemExit(
            f"SYM-3 benchmark mismatch: generated tables differ from {BENCH_MD.relative_to(REPO_ROOT)}. "
            f"{diff_hint}"
        )


def write_results_json(results: list[dict], primary: str) -> None:
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "git_sha": _git_sha(full=True),
        "git_sha_short": _git_sha(full=False),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_tokenizer": primary,
        "tokenizers": _tokenizer_metadata(),
        "benchmark_source": str(BENCH_MD.relative_to(REPO_ROOT)),
        "transcripts": results,
    }
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-md",
        action="store_true",
        help="Overwrite docs/sym3-bench.md with freshly computed tables (after local review).",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip comparison against committed sym3-bench.md (not for CI).",
    )
    args = parser.parse_args(argv)

    results, md, primary = run_all_benches()

    if not args.skip_verify:
        verify_against_committed(md)

    if args.write_md:
        BENCH_MD.write_text(_normalize_md(md), encoding="utf-8")
        print(f"Wrote {BENCH_MD}")

    write_results_json(results, primary)
    print(f"Wrote {RESULTS_JSON}")
    print("SYM-3 benchmark verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
