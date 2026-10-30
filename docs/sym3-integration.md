# SYM-3 in Synbios

Synbios records forge lifecycle traffic as structured commands (`task.claim`, `artifact.add`, and so on). When agents exchange that traffic over model-billed channels, **token count on the wire** matters more than human-readable JSON. **SYM-3** is the tokenizer-aware wire format Synbios uses for that integration.

## Where the spec lives

The canonical SYM protocol home is **[aska-digital/protean-sym2p](https://github.com/aska-digital/protean-sym2p)**. Language spec, paper, reproducible benchmark publication, citation metadata, and project site will be maintained there (DOI pending). This repo contains the **Synbios-specific** encoder integration, synthetic lifecycle fixtures, and verified bench tables in [sym3-bench.md](sym3-bench.md).

## What lives in this repository

| Path | Role |
| --- | --- |
| `synbios/sym3/` | Encoders, lexicon, session state, content store, decode context sizing |
| `synbios/sym3/fixtures.py` | Synthetic forge lifecycles (11 / 40 / 200 messages) used for bench |
| `synbios/sym3/bench.py` | Baseline comparisons (JSON, English, TOON, Agora envelope, SYM-2P, SYM-3 variants) |
| `synbios/sym3/reproduce.py` | Regenerate tables, verify against committed markdown, write results JSON |
| `docs/sym3-bench.md` | Committed token accounting (primary: setup min + messages, o200k) |
| `tests/test_sym3.py` | Round-trip and minimal-context decode tests |

SYM-3 lines are **lossless** relative to canonical forge payloads for the tested fixtures: given decode-sufficient context (transcript-minimal lexicon slice and positional schema), decoders reconstruct the same structured commands Synbios would accept from compact JSON.

## Encoders (summary)

- **Shared session state** — project, task, agent, and artifact IDs collapse to short wire tokens after first use.
- **Lexicon** — command and enum strings chosen for low **o200k** token cost (`lexicon.json`, regeneratable via `generate_lexicon.py`).
- **Variants** — delta, content-addressed refs, positional fields, default omission, combined, and adaptive per-message selection (see module `encoders.py`).

Setup tokens are counted honestly: **minimal** context includes only mappings used in the transcript; **full** context includes the committed lexicon and complete positional schema (see `decoder_context.py`).

## Running the integration bench

```sh
python -m pip install -e .
python -m pip install -r requirements-bench.txt
make bench
```

See [sym3-bench-reproduce.md](sym3-bench-reproduce.md). CI runs the same verification on pull requests.

## Relation to Synbios API traffic

Today SYM-3 is a **reference integration** and benchmark harness inside the Python package, not the default HTTP API serialization. Forge HTTP and CLI traffic remain JSON. SYM-3 demonstrates how Synbios command shapes compress when agents share state and repeated digests across many messages—the pattern intended for agent-to-agent channels built on top of or beside the forge API.
