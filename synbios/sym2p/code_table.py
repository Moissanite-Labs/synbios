"""Versioned SYM-2P v2 code table (protean draft + Synbios forge extensions)."""
from __future__ import annotations

import hashlib
import json

from synbios.store import COMMAND_FIELDS

# Protean SPEC-V2-DRAFT core registries (codes 1-10 / 0 unset).
ROLES = {
    0: "reserved",
    1: "coordinator",
    2: "builder",
    3: "verifier",
    4: "scout",
    5: "critic",
    6: "operator",
}
ACTS = {
    0: "none",
    1: "assign",
    2: "acknowledge",
    3: "assert",
    4: "update",
    5: "receipt",
    6: "challenge",
    7: "dispute",
    8: "authorize",
    9: "query",
    10: "inform",
}
STATES = {
    0: "none",
    1: "proposed",
    2: "accepted",
    3: "rejected",
    4: "verified",
    5: "open",
    6: "closed",
    7: "superseded",
    8: "expired",
}
RQS = {0: "none", 1: "acknowledgement required", 2: "verification required"}

# Synbios domain extensions (100+), stable for this table version.
ROLE_FORGE = 100
OP_FORGE_CMD = 50
OP_FORGE_KV = 33
OP_FORGE_FIELD = 51
OP_SESSION_TABLE = 60
OP_SESSION_BIND = 61
OP_SESSION_ACTOR = 62
OP_FORGE_HEADER_F = 53
OP_FORGE_HEADER_PRJ = 54
OP_FORGE_TAILS = 56

V1_ACT_TO_V2 = {
    "assign": 1,
    "accept": 2,
    "assert": 3,
    "reject": 3,
    "update": 4,
}
V1_ST_TO_V2 = {
    "observed": 1,
    "inferred": 1,
    "assumed": 1,
    "proposed": 1,
    "disputed": 3,
    "rejected": 3,
    "verified": 4,
}
V1_RQ_TO_V2 = {"ack": 1, "upd": 2, "ver": 2}

V2_ACT_TO_V1 = {
    1: "assign",
    2: "accept",
    3: "assert",
    4: "update",
}
V2_ST_TO_V1 = {
    1: "proposed",
    3: "disputed",
    4: "verified",
}

FORGE_FIELD_INDEX: dict[str, dict[str, int]] = {}
_FIELD_DECODE: dict[str, dict[int, str]] = {}
_idx = 1
for _action in sorted(COMMAND_FIELDS):
    FORGE_FIELD_INDEX[_action] = {}
    _FIELD_DECODE[_action] = {}
    for _field in sorted(COMMAND_FIELDS[_action]):
        FORGE_FIELD_INDEX[_action][_field] = _idx
        _FIELD_DECODE[_action][_idx] = _field
        _idx += 1

TABLE_DOCUMENT = {
    "profile": "synbios-forge-v2-pilot/1",
    "protean": {"roles": ROLES, "acts": ACTS, "states": STATES, "requests": RQS},
    "synbios": {
        "role_forge": ROLE_FORGE,
        "opcodes": {
            "forge_cmd": OP_FORGE_CMD,
            "forge_kv": OP_FORGE_KV,
            "forge_field": OP_FORGE_FIELD,
            "session_table": OP_SESSION_TABLE,
            "session_bind": OP_SESSION_BIND,
            "session_actor": OP_SESSION_ACTOR,
        },
        "field_index": FORGE_FIELD_INDEX,
    },
}


def table_hash() -> str:
    blob = json.dumps(TABLE_DOCUMENT, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def table_hash_short() -> str:
    return table_hash()[:16]
