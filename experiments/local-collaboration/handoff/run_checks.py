#!/usr/bin/env python3
"""Local acceptance collection. No dependency installation or Exo source edits."""
import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

def run(args, cwd=ROOT):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)
        return {"command": args, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": args, "exit_code": None, "error": str(error)}

def inventory(path):
    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        return {"state": "unavailable", "reason": "Directory does not exist"}
    result = {"state": "observed"}
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    for key, args in (("commit", ["rev-parse", "HEAD"]), ("branch", ["branch", "--show-current"]), ("status", ["status", "--porcelain=v1", "-z"])):
        try:
            p = subprocess.run(["git", "-C", str(target)] + args, capture_output=True, timeout=30, env=environment)
            if p.returncode:
                result[key] = {"state": "unavailable", "exit_code": p.returncode}
            elif key == "status":
                records = p.stdout.split(b"\0")
                changes, position = [], 0
                while position < len(records):
                    record = records[position]
                    position += 1
                    if not record:
                        continue
                    changes.append(record)
                    # With -z, rename/copy records carry a second raw pathname.
                    if b"R" in record[:2] or b"C" in record[:2]:
                        position += 1
                result["dirty_entries"] = len(changes)
                result["untracked_entries"] = sum(r[:2] == b"??" for r in changes)
            else:
                result[key] = p.stdout.decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.TimeoutExpired) as error:
            result[key] = {"state": "unavailable", "reason": type(error).__name__}
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exo-core")
    parser.add_argument("--exo-desktop")
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "macos-results" / stamp
    output.mkdir(parents=True, exist_ok=False)
    report = {"observed_at": stamp, "platform": platform.system(), "release": platform.release(),
              "macos_version": platform.mac_ver()[0], "machine": platform.machine(), "python": platform.python_version(),
              "scope": "Automated local acceptance only; browser rendering and actual harness integration require separate observations.",
              "checks": [], "checkouts": {}}
    suites = [("coordinator", ROOT / "prototype" / "test_coordinator.py", [sys.executable, "-m", "unittest", "discover", "-s", "prototype", "-v"]),
              ("demo", ROOT / "prototype" / "demo.py", [sys.executable, "prototype/demo.py"]),
              ("dashboard", ROOT / "dashboard", [sys.executable, "-m", "unittest", "discover", "-s", "dashboard", "-p", "test*.py", "-v"])]
    for name, required, command in suites:
        if not required.exists() or (name == "dashboard" and not list(required.glob("test*.py"))):
            observed = {"name": name, "state": "unavailable", "reason": "Required files missing"}
        else:
            observed = dict(run(command), name=name)
            observed["state"] = "passed" if observed.get("exit_code") == 0 else "failed"
        report["checks"].append(observed)
        print(name + ": " + observed["state"], flush=True)
    for name, path in (("exo_core", args.exo_core), ("exo_desktop", args.exo_desktop)):
        report["checkouts"][name] = inventory(path) if path else {"state": "not supplied"}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Local report: " + str(output / "report.json"))
    print("Review before sharing. Do not share dashboard access tokens.")
    return 0 if all(c["state"] == "passed" for c in report["checks"]) else 1

if __name__ == "__main__":
    raise SystemExit(main())
