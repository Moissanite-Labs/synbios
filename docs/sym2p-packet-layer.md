# SYM-2P packet layer (milestone 1 + v2 pilot)

Synbios can carry forge commands as [SYM-2P/1.0](https://github.com/aska-digital/protean-sym2p) packets: one canonical JSON object per line, validated by the pinned `vendor/protean-sym2p-v1.0.0/scripts/protean-sym2p/sym-validate.py` (tag `v1.0.0`). Rule L-18 (no latent channel) is unchanged; latent profiles are out of scope.

Dense **SYM-2P/2.0-draft** lines (pipe-separated, vendored at `vendor/protean-sym2p-v2-draft/`, commit in `SOURCE.json`) are supported as an **opt-in pilot**: `apply_v2_packet` decodes to a byte-identical canonical v1 line, then runs the same fail-closed v1 validation, grant checks, and hash-chained audit path as JSON/v1. v2 never bypasses validation.

## Layout

| Module | Role |
| --- | --- |
| `synbios/sym2p/codec.py` | v1 packet assembly; `ext.synbios` holds only the command name and optional id tails |
| `synbios/sym2p/v2_codec.py` | v2 dense encode/decode to canonical v1 |
| `synbios/sym2p/code_table.py` | Versioned registries + `table_hash()` |
| `synbios/sym2p/session.py` | Handshake + alias/actor resolution |
| `synbios/sym2p/fields.py` | Maps forge fields onto `cond`, `ops`, and header ids |
| `synbios/sym2p/adapter.py` | `apply_packet` (v1 JSON) and `apply_v2_packet` (opt-in v2) |
| `synbios/sym2p/audit.py` | Deterministic English audit line per packet |
| `synbios/sym2p/bench.py` | JSON vs v1 vs v2 raw vs v2 session size comparison |
| `synbios/sym2p/comprehension_check.py` | Offline fixture + harness (no model API calls) |

Forge events record `sym2p_packet_hash` and `sym2p_audit` when commands arrive through the adapter (v1 or v2).

`apply_packet` validates each v1 line in-process with the pinned `sym-validate.py` rules (canonical bytes, duplicate-key rejection, schema), rejects any `ext.synbios.payload`, checks `f` against the bearer actor, then decodes native fields only. Failures do not append audit events.

## Native mapping

Forge payloads are **not** duplicated under `ext.synbios`. The codec writes:

- **Header** (`v`, `id`, `tk`, `prj`, `f`, `t`, `a`, `s`, `st`, `rq`, `exp`) — routing, speech act, epistemic status.
- **`cond`** — string fields and JSON-valued lists (prefix `synbios/…`); used for project/principal/grant/evidence/review text.
- **`ops`** — `update` deltas (`set` / `add`) for task criteria, artifact fields, task status transitions, etc., with `base:"forge:v1"`.
- **`ext.sym2p.rev`** — profile tag (sanctioned).
- **`ext.synbios` residue only:**
  - `cmd` — forge command discriminator (required).
  - `tails` — optional map of one hex character per role (`p`, `t`, `h`) when a 32-byte forge id is split to fit SYM id grammar in `tk`/`prj`/`s` (31 nybbles in the header + 1 nybble in `tails`).

Authoritative forge ids appear once on the wire: either in header sym ids (plus tail) or in `cond` (e.g. `grant.create` `principal_id`), not in both header and `cond` for the same field. `apply_packet` rejects any `ext.synbios.payload` blob; native fields are the only source of truth.

## v2 pilot (dense + session)

Wire format follows `vendor/protean-sym2p-v2-draft/SPEC-V2-DRAFT.md` (13 `|`-separated fields). Synbios extends the body opcode registry in `code_table.py` (domain codes 33–62, forge role code 100). Each v2 message after handshake carries `(60 <table_hash>)` in the body; unknown aliases or hash mismatch fail closed.

Session handshake (once per peer context) binds:

- code-table hash (short prefix of `table_hash()`),
- project hex (`61 p …`),
- id aliases (`61 <alias> <role> <hex32>`),
- actor codes for senders (`62 <code> h|a <hex32>`).

Steady-state packets use alias tokens in `TK` (`p` or `t`) and indexed field opcodes `(51 idx "value")` instead of repeating JSON keys.

## Verdict (this workload)

For the 11-command lifecycle bench, **SYM-2P v1 does not beat plain JSON on tokens**. Native `cond`/`ops` content is already slightly smaller than JSON POST bodies; the v1 SYM envelope dominates.

**v2 with session context does not beat plain JSON on tokens** for this 11-command transcript. Steady-state v2 session messages total **1202** tokens vs **683** for JSON POST bodies; including the one-time handshake (**212** tokens) the session transcript is **1415** tokens. v2 session is still a large win over v1 (**2720** tokens) because the JSON envelope disappears in favor of dense fields and indexed payload opcodes.

What v1/v2 still buy besides raw size:

- **Validator** — pinned fail-closed checks (v1 JSON; v2 shape via vendored grammar + Synbios opcodes).
- **Stable ids and roles** — SYM grammar and session aliases instead of anonymous JSON.
- **Audit** — deterministic English lines tied to speech acts and native fields.
- **Hash-chained log** — `sym2p_packet_hash` over the canonical v1 line (including after v2 decode).

## Bench (representative lifecycle)

```bash
python3 -m synbios.sym2p.bench
```

Re-run for your checkout; example with `tiktoken o200k_base`:

```
Forge lifecycle transcript (11 commands). Tokenizer: tiktoken o200k_base.
Format                                      Bytes   Tokens
----------------------------------------------------------
JSON API POST bodies                         1767      683
SYM-2P v1 (Synbios codec)                    5445     2720
  v1 envelope (header + ext)                 3419     2095
  v1 content (cond + ops)                    2026      625
SYM-2P v2 raw (no session)                   …        …
SYM-2P v2 session (steady state)               …        …
  v2 session handshake (once)                  …        …
  v2 session + handshake (total)               …        …
  v2 session amortized per msg                 …        …
```

(Paste the exact table from `python3 -m synbios.sym2p.bench` in PR evidence.)

## Comprehension check (offline)

```bash
python -m synbios.sym2p.comprehension_check
```

Uses `comprehension_fixture.json` with fixed v2 lines and expected English audit meanings. Intended for future LLM comprehension experiments; this harness does not call paid APIs.

## Usage

```python
from synbios.sym2p import (
    EncodeContext,
    encode_command,
    apply_packet,
    apply_v2_packet,
    forge_session_from_lifecycle,
    encode_v2_session,
)

ctx = EncodeContext(
    packet_id="c001",
    project_hex=project_id,
    task_hex=task_id,
    sender_hex=actor_id,
    sender_human=True,
    step=1,
)
line = encode_command("task.claim", {"task_id": task_id}, ctx)
apply_packet(store, token, line)

hs, session = forge_session_from_lifecycle(
    project_hex=project_id,
    task_hex=task_id,
    actors=[(10, actor_id, True)],
)
apply_v2_packet(store, token, encode_v2_session(line, session), session)
```

Validate emitted v1 lines:

```bash
python3 vendor/protean-sym2p-v1.0.0/scripts/protean-sym2p/sym-validate.py packets.jsonl
```

Validate v2 dense lines:

```bash
python3 vendor/protean-sym2p-v2-draft/scripts/protean-sym2p/sym2-validate.py packets.v2.txt
```

(Synbios forge body opcodes 33–62 are validated in-process by `v2_wire.py`; the vendored validator covers core opcodes 10–22.)
