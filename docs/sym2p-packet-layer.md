# SYM-2P packet layer (milestone 1)

Synbios can carry forge commands as [SYM-2P/1.0](https://github.com/aska-digital/protean-sym2p) packets: one canonical JSON object per line, validated by the pinned `vendor/protean-sym2p-v1.0.0/scripts/protean-sym2p/sym-validate.py` (tag `v1.0.0`, commit `43334b2`). Rule L-18 (no latent channel) is unchanged; latent profiles are out of scope for this milestone.

## Layout

| Module | Role |
| --- | --- |
| `synbios/sym2p/codec.py` | Lossless encode/decode of `/api/commands/{action}` payloads via `ext.synbios` |
| `synbios/sym2p/adapter.py` | Applies a packet line through `Store.command` |
| `synbios/sym2p/audit.py` | Deterministic English audit line per packet |
| `synbios/sym2p/bench.py` | JSON vs v1 vs v2 draft size comparison |

Forge events record `sym2p_packet_hash` (SHA-256 of the UTF-8 packet line) and `sym2p_audit` when commands arrive through the adapter.

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

Benchmark (also run in CI):

```bash
python3 -m synbios.sym2p.bench
```

## Bench results (representative lifecycle transcript)

Run `python3 -m synbios.sym2p.bench` for current numbers. Example (11 commands, tiktoken `o200k_base`):

```
Forge lifecycle transcript (11 commands). Tokenizer: tiktoken o200k_base.
Format                                      Bytes   Tokens
----------------------------------------------------------
JSON API POST bodies                         1767      683
SYM-2P v1 (Synbios codec)                    5091     2727
SYM-2P v2 draft (measurement only)           2851     1454
```

For milestone 1 the v1 wrapper is larger than raw JSON because the forge command object is carried losslessly inside `ext.synbios` while still satisfying the SYM-2P envelope and validator. v2 figures use the draft positional wire from `SPEC-V2-DRAFT.md` on `protean-sym2p` main and are measurement-only.

## Spec notes

- Wire `v` is integer `2`; profile name SYM-2P/1.0 travels in `ext.sym2p.rev`.
- Synbios command bodies live under experimental `ext.synbios` (`cmd` + `payload`) so decoders recover the exact JSON API object without inferring from speech acts alone.
- Header `f`/`t`/`tk`/`prj` ids use deterministic `sym_id` prefixes for validator grammar; authoritative hex ids remain inside `payload`.
