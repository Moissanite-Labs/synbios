#!/usr/bin/env python3
"""Export seeded demo state for the static GitHub Pages client."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from synbios.demo import seed_demo
from synbios.store import Store


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "web/src/demo/fixture.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    directory = tempfile.mkdtemp(prefix="synbios-demo-export-")
    db_path = str(Path(directory) / "demo.db")
    record = seed_demo(db_path)
    store = Store(db_path)
    try:
        state, events = store._load()
        public_state = {
            key: state[key]
            for key in ("projects", "tasks", "principals", "grants")
        }
        fixture = {
            "synthetic": True,
            "message": record["message"],
            "tokens": {
                "operator": record["token"],
                "reviewer": record["reviewer_token"],
                "agent": record["agent_token"],
            },
            "state": public_state,
            "credentials": state["credentials"],
            "events": events,
        }
        out.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
