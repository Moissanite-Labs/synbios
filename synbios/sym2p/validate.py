"""In-process SYM-2P/1.0 wire validation (vendored sym-validate logic)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .codec import SYNBIOS_EXT_VER
from .errors import PacketRejected

_VENDOR = (
    Path(__file__).resolve().parents[2]
    / "vendor"
    / "protean-sym2p-v1.0.0"
    / "scripts"
    / "protean-sym2p"
    / "sym-validate.py"
)
_MODULE = None


def _validator():
    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("_sym_validate_vendor", _VENDOR)
        if spec is None or spec.loader is None:
            raise RuntimeError("sym-validate.py not found")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


def _check_synbios_ext(packet: dict) -> None:
    ext = packet.get("ext")
    if not isinstance(ext, dict):
        raise PacketRejected("packet missing ext")
    syn = ext.get("synbios")
    if not isinstance(syn, dict):
        raise PacketRejected("packet missing ext.synbios")
    if syn.get("v") != SYNBIOS_EXT_VER:
        raise PacketRejected("unsupported ext.synbios version")
    if "payload" in syn:
        raise PacketRejected("ext.synbios.payload is not permitted; use native cond/ops fields")
    if not isinstance(syn.get("cmd"), str):
        raise PacketRejected("invalid ext.synbios.cmd")


def validate_wire_line(line: str) -> dict:
    """Validate canonical SYM-2P bytes and schema; return parsed packet."""
    text = line.strip()
    if not text:
        raise PacketRejected("empty packet line")
    mod = _validator()
    findings: list = []
    if mod._noncanonical(text):
        findings.append(
            mod.E("ERR:SYN", "<document>", "not canonical compact serialization (L-3/L-4, M-2)")
        )
    packet = mod.parse_json(text, findings)
    if packet is None:
        msg = findings[0]["msg"] if findings else "invalid JSON"
        raise PacketRejected(msg)
    if not isinstance(packet, dict):
        raise PacketRejected("packet must be a JSON object")
    mod.validate_packet(packet, findings)
    if findings:
        raise PacketRejected(findings[0]["msg"])
    _check_synbios_ext(packet)
    return packet
