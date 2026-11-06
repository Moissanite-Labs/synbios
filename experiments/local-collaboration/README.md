# Local multi harness collaboration experiment

Independent agent sessions can invalidate each other's assumptions while editing the same codebase. This experiment supplies a local coordinator and Crystal Lattice dashboard for declaring work, observing overlapping scopes and stale baselines, and retaining alternative records over an ordinary existing folder. Git and any particular model provider are optional.

This is an isolated experimental surface, not a change to Synbios task acceptance, grants, review authority or the installed Exo runtime. It does not apply source edits, create isolated candidate copies, launch agents or supply native commercial-harness adapters. Actor names and candidate selections are caller assertions. Coordination is cooperative, not a filesystem security boundary or formal proof.

## Run locally

From this directory, with Python 3.11 or newer (matching Synbios):

```sh
python3 handoff/run_checks.py
python3 handoff/start_rehearsal.py
```

The rehearsal creates a disposable folder and prints a loopback dashboard URL. It starts with no invented agents or work. Register names, declare scopes, inspect conflicts and retain alternatives through the UI. Ctrl+C stops that rehearsal and removes its temporary state. Existing projects and running Exo applications are untouched.

- [Coordinator contract and limits](prototype/README.md)
- [Dashboard launch, API and trust boundaries](dashboard/README.md)
- [Mac Codex CLI handoff and browser acceptance](handoff/START-HERE.md)
- [Design and repository boundaries](DESIGN.md)

## Verification

```sh
python3 -m unittest discover -s prototype -v
python3 prototype/demo.py
python3 -m unittest discover -s dashboard -p 'test_*.py' -v
python3 handoff/bootstrap_exo.py   # once: installs pinned Exo from GitHub for harness tests
python3 -m unittest discover -s harness -p 'test_harness_adapters_integration.py' -v
```

The coordinator suite includes six synchronized processes, durable registration, all pairwise overlaps, directory membership changes, byte-level staleness and rollback. HTTP tests exercise actual SQLite mutations and compare them with a separate CLI process. A Linux Chromium smoke check exercised real dashboard forms, conflicts, stale observations, selection persistence, CLI parity and layout widths of 390 and 1440 pixels without JavaScript errors. The harness integration suite exercises two adapter kinds (Exo core via `exo serve` with the echo engine and a distinct CLI subprocess worker) with process and JSON evidence files under disposable temp directories: reconnect, stop, crash ambiguity (process gone, process hung, coordinator row still active), and scope checks (respect vs reported violation). macOS, Windows, screen-reader and complete keyboard acceptance remain unrun. These checks do not establish formal verification.

The handoff writes reports locally under macos-results; do not commit these reports, databases, credentials, personal paths or local exports. No third-party dependencies or model calls are required. The experiment is not included in the Synbios wheel or production server.
