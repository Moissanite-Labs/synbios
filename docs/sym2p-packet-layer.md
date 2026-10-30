# SYM-2P packet layer (milestone 1)

Synbios can carry forge commands as [SYM-2P/1.0](https://github.com/aska-digital/protean-sym2p) packets: one canonical JSON object per line, validated by the pinned `vendor/protean-sym2p-v1.0.0/scripts/protean-sym2p/sym-validate.py` (tag `v1.0.0`). Rule L-18 (no latent channel) is unchanged; latent profiles are out of scope.

## Layout

| Module | Role |
| --- | --- |
| `synbios/sym2p/codec.py` | Packet assembly; `ext.synbios` holds only the command name and optional id tails |
| `synbios/sym2p/fields.py` | Maps forge fields onto `cond`, `ops`, and header ids |
| `synbios/sym2p/adapter.py` | Applies a packet line through `Store.command` |
| `synbios/sym2p/audit.py` | Deterministic English audit line per packet |
| `synbios/sym2p/bench.py` | JSON vs v1 vs v2 draft size comparison |

Forge events record `sym2p_packet_hash` and `sym2p_audit` when commands arrive through the adapter.

`apply_packet` validates each line in-process with the pinned `sym-validate.py` rules (canonical bytes, duplicate-key rejection, schema), rejects any `ext.synbios.payload`, checks `f` against the bearer actor, then decodes native fields only. Failures do not append audit events.

## Native mapping

Forge payloads are **not** duplicated under `ext.synbios`. The codec writes:

- **Header** (`v`, `id`, `tk`, `prj`, `f`, `t`, `a`, `s`, `st`, `rq`, `exp`) — routing, speech act, epistemic status.
- **`cond`** — `synbios/<field>=<value>` lines for project/principal/grant/evidence/review text. Values are verbatim strings, even when they look like JSON; only `capabilities` is JSON-encoded. Repeated `assumptions` lines form that list.
- **`ops`** — `update` deltas (`set` / `add`) for task criteria, artifact fields, task status transitions, etc., with `base:"forge:v1"`.
- **`ext.sym2p.rev`** — profile tag (sanctioned).
- **`ext.synbios` residue only:**
  - `cmd` — forge command discriminator (required).
  - `tails` — optional map of one hex character per role (`p`, `t`, `h`) when a 32-byte forge id is split to fit SYM id grammar in `tk`/`prj`/`s` (31 nybbles in the header + 1 nybble in `tails`).

Authoritative forge ids appear once on the wire: either in header sym ids (plus tail) or in `cond` (e.g. `grant.create` `principal_id`), not in both header and `cond` for the same field. `apply_packet` rejects any `ext.synbios.payload` blob; native fields are the only source of truth.

## Verdict (this workload)

For the 11-command lifecycle bench, **SYM-2P v1 does not beat plain JSON on tokens today**. With native mapping, v1 is still larger than POST bodies because JSON field names are repeated in `cond`/`ops` paths and SYM envelope fields add overhead on every line.

What v1 buys besides raw size:

- **Validator** — pinned `sym-validate.py` fail-closed checks (grammar, key order, acts, ops).
- **Stable ids and roles** — `f`/`t`/`tk`/`prj`/`s` in SYM grammar instead of anonymous JSON.
- **Audit** — deterministic English lines tied to speech acts and `cond`/`ops`.
- **Hash-chained log** — `sym2p_packet_hash` over the canonical packet line.

v2 draft numbers in the bench are measurement-only; v2 is not wired into Synbios.

## Bench (representative lifecycle)

```bash
python3 -m synbios.sym2p.bench
```

Example (`tiktoken o200k_base`; re-run for your checkout):

```
Forge lifecycle transcript (11 commands). Tokenizer: tiktoken o200k_base.
Format                                      Bytes   Tokens
----------------------------------------------------------
JSON API POST bodies                         1767      683
SYM-2P v1 (Synbios codec)                    5445     2720
  v1 envelope (header + ext)                 3419     2095
  v1 content (cond + ops)                    2026      625
SYM-2P v2 draft (measurement only)           2851     1454
```

On this transcript, **forge field data encoded in `cond`/`ops` (625 tokens) is already slightly smaller than the JSON POST bodies (683 tokens)**. Total v1 loses because the per-packet SYM envelope (2095 tokens across 11 lines) dominates.

## Usage

```python
from synbios.sym2p import EncodeContext, encode_command, apply_packet

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
```

Validate emitted lines:

```bash
python3 vendor/protean-sym2p-v1.0.0/scripts/protean-sym2p/sym-validate.py packets.jsonl
```
