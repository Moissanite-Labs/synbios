# Run the Exo collaboration experiment on macOS

Give Codex CLI this instruction from the unpacked workspace:

> Read handoff/START-HERE.md and README.md. Run python3 handoff/run_checks.py with the actual Exo core and desktop checkout paths if available. Inspect the existing checkouts read-only. Run the documented local dashboard against a separate temporary rehearsal folder first. Confirm its actual browser-to-backend-to-CLI behavior and report results under macos-results. Preserve all existing source changes and running applications. Do not merge, deploy, install over Exo, alter credentials, run paid model calls, or claim unsupported harness integrations. Do not weaken tests to obtain a pass. Record exact failures and platform limitations.

## What is in this bundle

A proposed portable collaboration architecture grounded in Moissanite Labs, founder intent and research records, a Python standard-library coordinator, and a local dashboard backend and interface. This experiment does not yet connect all of your live agents or apply their source edits.

Main implementation direction: Synbios for the collaboration feature, Exo for runtime/harness integration. Exoframe supplies the existing Crystal Lattice design; it is not the coordinator backend. Read [the design and repository boundaries](../DESIGN.md).

## Initial commands

Run from this directory's parent (the experiment root):

Use Python 3.11 or newer for the complete dashboard bundle. No third-party packages are required.

```sh
sw_vers -productVersion
uname -m
python3 --version
python3 handoff/run_checks.py
python3 handoff/start_rehearsal.py
```

If your checkouts are known, add them as individual quoted arguments:

```sh
python3 handoff/run_checks.py --exo-core "/actual/path/to/exo" --exo-desktop "/actual/path/to/exo-desktop"
```

The check runner records OS/Python metadata, runs the coordinator and dashboard suites plus the coordinator demo, and writes local reports to macos-results/. Exo paths are inspected only for commit, branch and dirty/untracked counts. Their contents are not copied. It does not install dependencies or restart Exo. The tests create disposable fixtures and start temporary loopback HTTP servers. The rehearsal launcher then prints a disposable folder and a local dashboard URL. It starts empty, so every actor and intention you see comes from your own registration. Ctrl+C ends only the launched rehearsal and removes its temporary state.

Read [the dashboard instructions](../dashboard/README.md) for the exact current launch command. Keep its SQLite database outside the target folder. Start with a disposable rehearsal folder, not your installed app or an active agent's worktree.

## Browser acceptance

1. Open the locally printed dashboard URL. Keep any access token private.
2. Register a test actor and declare a narrow read/write scope through a supported control.
3. Reload. Confirm the declaration persists and is visible through the coordinator CLI status against the same database.
4. Declare an overlapping scope for another actor and confirm the conflict is shown.
5. Change a fixture file outside the coordinator, refresh and confirm its baseline is stale.
6. Retain two labeled alternatives. Change a comparison label and confirm both alternatives remain.
7. Report console/rendering issues, keyboard navigation, readability and reduced-motion behavior. Never describe a comparison label as an actual code merge.

Record results in macos-results/browser-notes.md. Include actual app versions when testing a harness. Automated HTTP checks do not establish that the browser rendered correctly.

## Real Exo enrollment comes after the rehearsal

Inventory current revisions, dirty state, running checkout and existing Swarm PR ownership. Register narrow intentions against the identified development folders without applying changes. Keep core and desktop separate, and follow the canonical upstream/sync workflow. Do not change a running installation as part of acceptance.

A check failure is useful evidence. Preserve its output and stop the dependent step; continue unrelated read-only checks. Platform uncertainty stays visible. Review local reports before sharing; no credentials, tokens or private logs are needed.
