#!/usr/bin/env python3
"""Offline comprehension fixture for SYM-2P v2 (no model calls).

Run: python -m synbios.sym2p.comprehension_check
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from synbios.sym2p.session import SessionContext, forge_session_from_lifecycle
from synbios.sym2p.v2_codec import decode_v2_to_v1, encode_v2_session
from synbios.sym2p.codec import EncodeContext, encode_command
from synbios.sym2p.audit import render_audit_line

FIXTURE_PATH = Path(__file__).with_name("comprehension_fixture.json")


@dataclass
class Case:
    wire: str
    expected_meaning: str


def load_cases() -> list[Case]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [Case(**item) for item in raw["cases"]]


def decode_meaning(wire: str, session: SessionContext) -> str:
    v1 = decode_v2_to_v1(wire, session)
    packet = json.loads(v1)
    action = packet["ext"]["synbios"]["cmd"]
    actor = {"name": "fixture-actor", "kind": "agent"}
    from synbios.sym2p.codec import decode_command

    decoded_action, payload = decode_command(packet)
    if decoded_action != action:
        raise ValueError("cmd mismatch")
    return render_audit_line(decoded_action, payload, actor)


def main() -> int:
    project = "a1" * 16
    task = "b2" * 16
    sender = "d4" * 16
    agent = "c3" * 16
    _hs, session = forge_session_from_lifecycle(
        project_hex=project,
        task_hex=task,
        actors=[(10, sender, True), (11, agent, False)],
    )
    failures = 0
    for case in load_cases():
        meaning = decode_meaning(case.wire, session)
        if meaning != case.expected_meaning:
            print(f"FAIL: expected {case.expected_meaning!r} got {meaning!r}")
            failures += 1
        else:
            print(f"OK: {meaning}")
    if failures:
        print(f"{failures} comprehension case(s) failed")
        return 1
    print("all comprehension fixture cases passed")
    return 0


def regenerate_fixture() -> None:
    """Helper to rebuild fixture from sample commands (dev only)."""
    project = "a1" * 16
    task = "b2" * 16
    sender = "d4" * 16
    agent = "c3" * 16
    hs, session = forge_session_from_lifecycle(
        project_hex=project,
        task_hex=task,
        actors=[(10, sender, True), (11, agent, False)],
    )
    samples = [
        ("task.claim", {"task_id": task}, agent, False),
        ("task.transition", {"task_id": task, "status": "in_progress"}, agent, False),
    ]
    cases = []
    for idx, (action, payload, actor_hex, human) in enumerate(samples, start=1):
        ctx = EncodeContext(
            packet_id=f"x{idx:03d}",
            project_hex=project,
            task_hex=task,
            sender_hex=actor_hex,
            sender_human=human,
            step=idx,
        )
        v1 = encode_command(action, payload, ctx)
        wire = encode_v2_session(v1, session)
        actor = {"name": "fixture-actor", "kind": "agent" if not human else "human"}
        from synbios.sym2p.codec import decode_command
        from synbios.sym2p.canonical import parse_packet_line

        meaning = render_audit_line(action, payload, actor)
        cases.append({"wire": wire, "expected_meaning": meaning})
    FIXTURE_PATH.write_text(
        json.dumps({"handshake": hs, "cases": cases}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
