"""SYM-2P/1.0 codec for Synbios forge commands (lossless via ext.synbios)."""
from __future__ import annotations

from dataclasses import dataclass

from synbios.store import COMMAND_FIELDS

from .canonical import packet_line, parse_packet_line
from .ids import forge_role, sym_id

SYNBIOS_EXT_VER = 1
FORGE_RECIPIENT = "forge"

STATUS_TO_ST = {
    "open": "proposed",
    "in_progress": "inferred",
    "in_review": "proposed",
    "cancelled": "rejected",
    "accepted": "verified",
    "changes_requested": "disputed",
    "claimed": "assumed",
}

COMMAND_ACT = {
    "project.create": "assign",
    "principal.create": "assert",
    "principal.revoke": "reject",
    "grant.create": "assign",
    "grant.revoke": "reject",
    "task.create": "assign",
    "task.claim": "accept",
    "task.transition": "assert",
    "artifact.add": "assert",
    "evidence.add": "assert",
    "review.create": "accept",
}


@dataclass
class EncodeContext:
    packet_id: str
    project_hex: str
    task_hex: str | None
    sender_hex: str
    sender_human: bool
    step: int = 0

    @property
    def project_sym(self) -> str:
        return sym_id("p", self.project_hex)

    @property
    def task_sym(self) -> str:
        if self.task_hex:
            return sym_id("t", self.task_hex)
        return self.project_sym

    @property
    def sender_sym(self) -> str:
        return forge_role(self.sender_hex, human=self.sender_human)


def _subject_ref(action: str, payload: dict, ctx: EncodeContext) -> str | None:
    if action == "project.create":
        return ctx.project_sym
    if action in {"task.create", "task.claim", "task.transition", "artifact.add", "evidence.add", "review.create"}:
        task_id = payload.get("task_id") or ctx.task_hex
        if task_id:
            return sym_id("t", task_id)
    if action in {"grant.create", "grant.revoke"}:
        grant_or_task = payload.get("task_id")
        if grant_or_task and len(grant_or_task) == 32:
            return sym_id("t", grant_or_task)
    if action == "principal.revoke":
        principal = payload.get("principal_id")
        if principal:
            return sym_id("h", principal)
    return None


def _status_field(action: str, payload: dict) -> str | None:
    if action == "task.transition":
        return STATUS_TO_ST.get(payload.get("status"))
    if action == "review.create":
        return "verified" if payload.get("decision") == "approved" else "disputed"
    if action == "evidence.add":
        return "verified" if payload.get("status") == "passed" else "observed"
    return None


def build_packet(action: str, payload: dict, ctx: EncodeContext) -> dict:
    if action not in COMMAND_FIELDS:
        raise ValueError("unknown forge command")
    act = COMMAND_ACT[action]
    if action == "review.create" and payload.get("decision") == "changes_requested":
        act = "reject"
    packet = {
        "v": 2,
        "id": ctx.packet_id,
        "tk": ctx.task_sym,
        "prj": ctx.project_sym,
        "f": ctx.sender_sym,
        "t": FORGE_RECIPIENT,
        "a": act,
        "rq": "ack",
        "exp": ctx.step,
        "ext": {
            "sym2p": {"rev": "1.0"},
            "synbios": {"v": SYNBIOS_EXT_VER, "cmd": action, "payload": payload},
        },
    }
    subject = _subject_ref(action, payload, ctx)
    if subject:
        packet["s"] = subject
    status = _status_field(action, payload)
    if status:
        packet["st"] = status
    return packet


def encode_command(action: str, payload: dict, ctx: EncodeContext) -> str:
    return packet_line(build_packet(action, payload, ctx))


def decode_command(line: str) -> tuple[str, dict]:
    packet = parse_packet_line(line)
    ext = packet.get("ext")
    if not isinstance(ext, dict):
        raise ValueError("packet missing ext")
    syn = ext.get("synbios")
    if not isinstance(syn, dict):
        raise ValueError("packet missing ext.synbios")
    if syn.get("v") != SYNBIOS_EXT_VER:
        raise ValueError("unsupported ext.synbios version")
    action = syn.get("cmd")
    body = syn.get("payload")
    if not isinstance(action, str) or action not in COMMAND_FIELDS:
        raise ValueError("invalid ext.synbios.cmd")
    if not isinstance(body, dict):
        raise ValueError("invalid ext.synbios.payload")
    extra = set(body) - COMMAND_FIELDS[action]
    if extra:
        raise ValueError("unknown payload fields: " + ", ".join(sorted(extra)))
    return action, body


def packet_hash(line: str) -> str:
    import hashlib

    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
