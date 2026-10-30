"""SYM-2P/1.0 codec for Synbios forge commands (native fields + minimal ext.synbios)."""
from __future__ import annotations

from dataclasses import dataclass

from synbios.store import COMMAND_FIELDS

from .canonical import packet_line, parse_packet_line
from .fields import compute_tails, decode_native, encode_native
from .ids import forge_role, sym_id

SYNBIOS_EXT_VER = 2
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
    "artifact.add": "update",
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
    if action == "grant.create" and payload.get("task_id"):
        return sym_id("t", payload["task_id"])
    if action == "principal.revoke":
        return sym_id("h", payload["principal_id"])
    return None


def status_field(action: str, payload: dict) -> str | None:
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
    packet: dict = {
        "v": 2,
        "id": ctx.packet_id,
        "tk": ctx.task_sym,
        "prj": ctx.project_sym,
        "f": ctx.sender_sym,
        "t": FORGE_RECIPIENT,
        "a": act,
        "rq": "ack",
        "exp": ctx.step,
    }
    subject = _subject_ref(action, payload, ctx)
    if subject:
        packet["s"] = subject
    status = status_field(action, payload)
    if status:
        packet["st"] = status
    encode_native(action, payload, packet)
    tails = compute_tails(action, payload, packet)
    synbios_ext: dict = {"v": SYNBIOS_EXT_VER, "cmd": action}
    if tails:
        synbios_ext["tails"] = tails
    packet["ext"] = {"sym2p": {"rev": "1.0"}, "synbios": synbios_ext}
    return packet


def encode_command(action: str, payload: dict, ctx: EncodeContext) -> str:
    return packet_line(build_packet(action, payload, ctx))


def decode_command(packet: dict) -> tuple[str, dict]:
    ext = packet.get("ext")
    if not isinstance(ext, dict):
        raise ValueError("packet missing ext")
    syn = ext.get("synbios")
    if not isinstance(syn, dict):
        raise ValueError("packet missing ext.synbios")
    if syn.get("v") != SYNBIOS_EXT_VER:
        raise ValueError("unsupported ext.synbios version")
    if "payload" in syn:
        raise ValueError("ext.synbios.payload is not permitted")
    action = syn.get("cmd")
    if not isinstance(action, str) or action not in COMMAND_FIELDS:
        raise ValueError("invalid ext.synbios.cmd")
    body = decode_native(action, packet)
    extra = set(body) - COMMAND_FIELDS[action]
    if extra:
        raise ValueError("unknown payload fields: " + ", ".join(sorted(extra)))
    missing = COMMAND_FIELDS[action] - set(body)
    if missing:
        raise ValueError("missing payload fields: " + ", ".join(sorted(missing)))
    return action, body


def packet_hash(packet: dict) -> str:
    import hashlib

    return hashlib.sha256(packet_line(packet).encode("utf-8")).hexdigest()


def v1_size_breakdown(line: str) -> tuple[int, int, int]:
    """Return total bytes, envelope bytes (header + ext), content bytes (cond + ops)."""
    packet = parse_packet_line(line)
    envelope = {k: v for k, v in packet.items() if k not in ("cond", "ops")}
    total = len(line.encode("utf-8"))
    env_b = len(packet_line(envelope).encode("utf-8"))
    return total, env_b, total - env_b
