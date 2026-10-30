# SYM-3: Token-Aware Shared-State Messaging for Agent-to-Agent Communication

**Authors:** Ahraz Arifuddin (Moissanite Labs); grk-qalam (agent)

## Abstract

Agent-to-agent traffic is billed by tokenizer output, not by human readability. SYM-3 is a family of wire encodings for Synbios forge lifecycle messages that minimize **o200k_base** token cost under honest decoder setup accounting. Encoders share a tokenizer-tuned lexicon, session-scoped identifiers, optional content-addressed blobs, positional field schemas, default-value omission, and an adaptive mode that picks the cheapest variant per message. On an 11-message synthetic lifecycle, SYM-3 **refs** totals **491** tokens (setup min + messages) versus **682** for compact JSON and **686** for lossless English; savings grow on 40- and 200-message transcripts. Setup tokens are counted in a **decode-sufficient** minimal form (mappings used in the transcript only). Negative results from SYM-2P dense symbolic pilots and multilingual lexicon candidates are reported. Model comprehension on the wire format remains under evaluation.

## Motivation

Multi-agent systems exchange structured commands—task claims, artifact hashes, evidence bindings—at scale. When both endpoints are language models or model-backed services, the dominant cost is **tokens on the wire**, not bytes or JSON prettiness. Human operators rarely read raw agent traffic; protocols may use opaque tokens, positional fields, and shared state as long as decoders can reconstruct canonical payloads.

SYM-3 targets **lossless** reconstruction of forge commands relative to compact JSON baselines, while accepting one-time decoder context (lexicon slice + schema) that must be present or cached for decode. Comparisons use tokenizer-accurate counting, not character length or heuristics.

## Prior work

**Agora** ([arXiv:2410.11905](https://arxiv.org/abs/2410.11905)) describes hash-referenced, content-addressed agent envelopes; SYM-3 **refs** follows a similar content-store pattern and is the closest prior-art row in our benchmark.

**TOON** (`toon-format`) provides a compact textual serialization for nested structures; we include a TOON baseline on the same fixtures.

**LLMLingua / LLMLingua-2** compress natural-language prompts by dropping tokens; they optimize single-turn context, not a **session** with evolving shared state and repeated digests.

**Chain of Draft** motivates terse natural-language drafts; we benchmark an English terse lossless line format in that spirit.

**A2A** and **MCP** standardize agent discovery and tool/context channels; SYM-3 is complementary wire compression for an application-specific command stream, not a replacement for either protocol.

**Multilingual tokenizer fertility:** Petrov et al. (2023) show non-English text is not uniformly cheaper under byte-level BPE; our lexicon generator rejected non-English wire tokens that did not reduce **o200k** counts (see negative results).

## Method

SYM-3 messages are line-oriented text. A session tracks project, task, agent, and artifact identifiers; repeated UUIDs collapse to single-character wire tokens (`p`, `t`, `a`, …). A **tokenizer-cost lexicon** maps command names, status/kind enums, and format tags to strings chosen by minimum max-token count across configured encodings (primary: **o200k_base**).

**State deltas:** the delta encoder emits only fields that change relative to session state instead of full canonical payloads.

**Content-addressed refs:** large or repeated string/blob values hash to stable ref tokens once published in a session content store (Agora-like).

**Positional schemas:** fixed field order per command reduces key overhead.

**Default omission:** fields equal to schema defaults are dropped on the wire when safe.

**Adaptive encoding:** per message, the implementation selects the cheapest among delta, refs, positional, omit, and combined variants (format tag prefix on each line).

**Decoder context:** decoders need a **decode-sufficient** prefix: wire mappings for every command, status, kind, and format tag **used in the transcript** (for adaptive, all format tags). A **full** setup includes the committed lexicon JSON and complete positional schema; benchmarks report both. **Cached†** totals assume one-time billing of 10% of minimal setup (not API-measured).

Round-trip goal: given decoder context + lines, reconstruct canonical JSON-equivalent payloads (see unit tests); **decode-sufficient minimal context** is the primary setup column in results.

## Negative results

**SYM-2P v1** on `lifecycle_11` costs **2719** message tokens (primary total **2719**) versus compact JSON **682**—dense symbolic packet encoding without shared-state wins is unusable for token billing.

**SYM-2P v2** session + handshake (PR #6 dense pilot): setup **213**, messages **1202**, total **1415** on 11 messages—still above JSON **682**; handshaked dense codes tokenize poorly on **o200k**.

**Multilingual / non-English lexicon candidates:** words chosen for human brevity did not reduce **o200k** token counts versus ASCII wire tokens; the committed lexicon stays tokenizer-tuned, not natural-language shortcuts.

## Results

All numbers below are taken from [sym3-bench.md](../sym3-bench.md). Primary accounting: **setup (min, decode-sufficient) + messages**, **o200k_base**.

### lifecycle_11 (11 messages)

| Format | setup (min) | messages | total (primary) |
| --- | ---: | ---: | ---: |
| compact JSON | 0 | 682 | 682 |
| English (lossless) | 0 | 686 | 686 |
| SYM-3 refs | 250 | 241 | **491** |
| SYM-3 adaptive | 271 | 241 | **512** |
| SYM-3 combined | 250 | 334 | 584 |
| SYM-3 delta | 250 | 349 | 599 |
| Agora envelope | 48 | 979 | 1027 |
| TOON | 0 | 805 | 805 |

Under **full** setup (524 + messages), SYM-3 refs/adaptive totals **765**—above compact JSON at 11 messages. Do not compare against English (lossy summary) for information equivalence.

**Break-even (messages to beat compact JSON / lossless English):** adaptive **7** / **7**; refs **7** / **7**; combined **8** / **8**; delta **9** / **9**; omit **9** / **9**; positional **7** / **7**.

### lifecycle_40 (40 messages)

| Format | total (primary) | total (cached†) |
| --- | ---: | ---: |
| compact JSON | 5343 | 5343.0 |
| English (lossless) | 5242 | 5242.0 |
| SYM-3 adaptive | **1738** | 1490.5 |
| SYM-3 refs | **1717** | 1488.4 |
| SYM-3 combined | 2566 | 2337.4 |

Break-even vs compact JSON: adaptive **3**, refs **3**, combined **4**, delta **6**, omit **6**, positional **4** messages.

### lifecycle_200 (200 messages)

| Format | total (primary) | total (cached†) |
| --- | ---: | ---: |
| compact JSON | 27363 | 27363.0 |
| English (lossless) | 26754 | 26754.0 |
| SYM-3 adaptive | **7649** | 7401.5 |
| SYM-3 refs | **7628** | 7399.4 |
| SYM-3 combined | 11873 | 11644.4 |

Break-even vs compact JSON: adaptive **3**, refs **3**, combined **4**, delta **6**, omit **6**, positional **4** messages.

### Verdict

On the shortest transcript, SYM-3 **refs** and **adaptive** beat compact JSON and lossless English under primary accounting. Savings increase with transcript length and repeated content. Cached† totals improve further but rely on the 10% setup assumption.

## Model comprehension

> **Status:** pending — do not cite accuracy numbers yet.

| Metric | Encoder variants | Result |
| --- | --- | --- |
| Decode accuracy (line → JSON) | delta, refs, positional, omit, combined, adaptive | TODO |
| State-question accuracy (session facts) | all | TODO |
| Generation round-trip (encode → model decode → re-encode) | all | TODO |

Optional harness: `python -m synbios.sym3.comprehension` (requires API key; skipped in CI).

## Limitations

- Savings depend on **repeated content and shared session state**; they scale with conversation length and redundancy, not single-turn prompts.
- **Single-turn inference** cost is unchanged; SYM-3 optimizes multi-message agent sessions.
- Counts use **o200k_base** as primary; other models may differ.
- Lifecycles are **synthetic** forge transcripts, not production traffic mixes.
- **Full** lexicon setup can erase wins on very short sessions (see 11-message full-setup row).
- Human readability and third-party auditability of raw lines are reduced by design.

## Reproduction

See [REPRODUCE.md](REPRODUCE.md). Summary: `make bench` after `pip install -r requirements-bench.txt`.

## References

- Agora: arXiv:2410.11905
- Petrov et al., 2023 — tokenizer fertility across languages
- LLMLingua / LLMLingua-2 — prompt token compression
- Chain of Draft — terse drafting for LLM I/O
- TOON — `toon-format` package
- Agent protocols: A2A, MCP (tool/context standards)
