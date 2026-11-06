#!/usr/bin/env python3
"""Launch the dashboard on disposable fixtures, never on an Exo installation."""
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="exo-weave-rehearsal-") as directory:
        base = Path(directory)
        target = base / "target"
        target.mkdir()
        (target / "example.txt").write_text("Rehearsal fixture, not Exo source.\n", encoding="utf-8")
        print("Disposable target: " + str(target), flush=True)
        print("No actors or activity are pre-populated. Ctrl+C ends this rehearsal and removes its state.", flush=True)
        child = subprocess.Popen([sys.executable, str(root / "dashboard/server.py"), "--db", str(base / "state.sqlite"), "--root", str(target), "--port", "0"])
        try:
            return child.wait()
        except KeyboardInterrupt:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
