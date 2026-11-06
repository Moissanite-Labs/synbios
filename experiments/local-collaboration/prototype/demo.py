"""Portable disposable demonstration. Run: python prototype/demo.py."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    script = Path(__file__).with_name("coordinator.py")
    with tempfile.TemporaryDirectory(prefix="weave-demo-") as temporary:
        base = Path(temporary)
        root = base / "existing-project"
        (root / "src").mkdir(parents=True)
        source = root / "src/example.txt"
        source.write_text("initial content\n")

        def run(*args):
            response = subprocess.run([sys.executable, str(script), "--db", str(base / "coordination.sqlite"), *args], text=True, capture_output=True, check=True)
            return json.loads(response.stdout)["result"]

        run("init", str(root))
        first = run("declare", "--actor", "codex-session", "--read", "src", "--write", "src/example.txt")
        second = run("declare", "--actor", "independent-cli", "--write", "src")
        a = run("alternative", first["intention"]["id"], "--label", "minimal edit", "--location", "external-candidate-A")
        run("alternative", first["intention"]["id"], "--label", "redesign", "--location", "external-candidate-B")
        run("alternative-status", a["id"], "--status", "testing")
        current = run("check", first["intention"]["id"])
        # The demo is an external editor; the coordinator never writes source.
        source.write_text("edited outside coordinator\n")
        stale = run("check", first["intention"]["id"])
        run("finish", second["intention"]["id"], "--status", "abandoned")
        status = run("status")
        assert current["state"] == "current" and stale["state"] == "stale"
        assert len(second["conflicts"]) == 2 and len(status["alternatives"]) == 2
        assert not status["conflicts"]
        print(json.dumps({"protocol": "weave.local.v1", "demo": "passed", "initial_conflicts": len(second["conflicts"]), "before_external_edit": current["state"], "after_external_edit": stale["state"], "preserved_alternatives": len(status["alternatives"]), "events": len(status["events"]), "temporary_workspace_removed_on_exit": True}, indent=2))


if __name__ == "__main__":
    main()
