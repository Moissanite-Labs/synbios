"""SYM-2P v1 integration for the Synbios local forge."""
from .adapter import apply_packet, apply_v2_packet
from .audit import render_audit_line
from .canonical import DuplicateKey, packet_line, parse_packet_line
from .codec import (
    EncodeContext,
    decode_command,
    encode_command,
    packet_hash,
    status_field,
    v1_size_breakdown,
)
from .code_table import table_hash, table_hash_short
from .errors import PacketRejected
from .session import SessionContext, apply_handshake, build_handshake_line, forge_session_from_lifecycle
from .validate import validate_wire_line
from .v2_codec import decode_v2_to_v1, encode_v2_raw, encode_v2_session

__all__ = [
    "DuplicateKey",
    "EncodeContext",
    "PacketRejected",
    "SessionContext",
    "apply_handshake",
    "apply_packet",
    "apply_v2_packet",
    "build_handshake_line",
    "decode_command",
    "decode_v2_to_v1",
    "encode_command",
    "encode_v2_raw",
    "encode_v2_session",
    "forge_session_from_lifecycle",
    "packet_hash",
    "packet_line",
    "parse_packet_line",
    "render_audit_line",
    "status_field",
    "table_hash",
    "table_hash_short",
    "validate_wire_line",
    "v1_size_breakdown",
]
