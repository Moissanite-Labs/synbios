# Reproducing the Synbios SYM-3 integration benchmark

Token counts in [sym3-bench.md](sym3-bench.md) are produced by the in-repo harness under `synbios/sym3/`. Primary accounting uses **o200k_base** via tiktoken: total = decode-sufficient setup (min) + message tokens.

The SYM protocol specification, research paper, canonical benchmarks publication, and project site live in **[aska-digital/protean-sym2p](https://github.com/aska-digital/protean-sym2p)** (SYM-3 language spec; DOI pending). This repository keeps the Synbios forge integration and a verified copy of the integration bench tables.

## One command

From the repository root, with Python 3.11+:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m pip install -r requirements-bench.txt
make bench
```

Equivalent:

```sh
python -m synbios.sym3.reproduce
```

This will:

1. Recompute all lifecycle tables (11, 40, and 200 messages).
2. Compare the generated markdown to the committed [docs/sym3-bench.md](sym3-bench.md) and **exit non-zero** on any mismatch.
3. Write [sym3-bench-results.json](sym3-bench-results.json) with structured results, pinned dependency versions, tokenizer metadata, and the current git SHA.

To refresh the committed tables after an intentional encoder or fixture change:

```sh
python -m synbios.sym3.reproduce --write-md
git diff docs/sym3-bench.md
```

## Pinned dependencies

Versions are pinned in [requirements-bench.txt](../requirements-bench.txt) (`tiktoken`, `toon-format`). CI installs the same file before running verification.

## Optional checks

- Regenerate markdown only (no verify): `python -m synbios.sym3.bench` (overwrites `docs/sym3-bench.md`).
- LLM comprehension experiments (requires `OPENAI_API_KEY`, not run in CI): `python -m synbios.sym3.comprehension`.

## Unit tests

```sh
python -m unittest discover -s tests -v
```

Tests cover SYM-3 round-trip encoding and bench invariants without network access.
