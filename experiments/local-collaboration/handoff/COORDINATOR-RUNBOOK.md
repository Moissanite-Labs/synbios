# Coordinator enrollment runbook for agent sessions

A machine-tested companion to [START-HERE.md](START-HERE.md) and the [onboarding issue](https://github.com/Moissanite-Labs/synbios/issues/58). This is the condensed per-session procedure an operator or agent session actually follows, including two baseline pitfalls observed during a macOS pilot.

The coordinator records assertions, not control: actor labels are caller-asserted, registration does not attach a live session, and `accepted`/`completed` are advisory. Integration always happens through the repository's normal review workflow.

## Setup once per machine

Requires Git and Python 3.11+ with SQLite. No third-party packages.

```sh
git clone https://github.com/Moissanite-Labs/synbios.git "$HOME/Developer/synbios-local-pilot"
cd "$HOME/Developer/synbios-local-pilot"
python3 -m venv .venv
export SYNBIOS_PY="$PWD/.venv/bin/python"
export SYNBIOS_LC="$PWD/experiments/local-collaboration"
```

Optionally run `$SYNBIOS_PY handoff/run_checks.py` from `$SYNBIOS_LC` and confirm the portable suites pass (`harness_exo_core` is an opt-in skip until `handoff/bootstrap_exo.py` is run).

## Setup once per coordination root

One database is bound to one root. State and candidate parents must live outside the registered root after symlink resolution.

```sh
export SYNBIOS_DB="$HOME/.local/state/synbios/<root-name>/weave.sqlite"
export SYNBIOS_CANDIDATES="$HOME/Developer/synbios-candidates/<root-name>"
mkdir -p "$(dirname "$SYNBIOS_DB")" "$SYNBIOS_CANDIDATES"

sc() { "$SYNBIOS_PY" "$SYNBIOS_LC/prototype/coordinator.py" --db "$SYNBIOS_DB" "$@"; }
sc init /absolute/path/to/shared/checkout
```

Optional dashboard (a viewer over the same database):

```sh
"$SYNBIOS_PY" "$SYNBIOS_LC/dashboard/server.py" --db "$SYNBIOS_DB" --port 0
# prints http://127.0.0.1:PORT/ — use the exact printed loopback host
```

Records survive a restart when the same `--db` is reused; reopen/reload the printed URL afterwards because the port changes with `--port 0`.

## Enroll each session

```sh
sc register-actor <unique-label>          # e.g. codex-mac-01; caller-asserted, not authenticated
sc declare --actor <label> \
  --read relative/path/to/shared-contract \
  --write relative/path/to/component
```

- Repeat `--read`/`--write` per dependency path. Do not declare `.` on a full checkout: scans include hidden files, build products and Git metadata, and symlinks in observed scopes are rejected.
- Save `result.intention.id`. A zero exit code only means registration succeeded — inspect the returned `conflicts` array and observation `state` fields (`stale`, `unverifiable`) before relying on them.
- A missing path is a valid baseline, so verify spelling rather than assuming registration proved existence.
- Overlapping work: agree on narrower scopes, sequence dependent changes, or give each session its own candidate. Never let two sessions edit the same candidate folder.

## Give each worker an isolated candidate

Two routes:

1. **Materialize from the root** (the documented default):

   ```sh
   sc alternative <INTENT_ID> --label <label>-attempt-a \
     --materialize git_worktree --materialize-parent "$SYNBIOS_CANDIDATES"
   ```

   A worktree starts from the root's **HEAD** and does not carry uncommitted changes. `copy` duplicates the whole tree including uncommitted/untracked content and follows symlinks; use it deliberately on small, inspected trees.

2. **Register an externally prepared directory** — important when the shared root is stale or dirty:

   ```sh
   git -C <shared-root> worktree add --detach "$SYNBIOS_CANDIDATES/<name>" origin/main
   sc alternative <INTENT_ID> --label <label>-attempt-a --location "$SYNBIOS_CANDIDATES/<name>"
   ```

## Work lifecycle

```sh
sc check <INTENT_ID>
sc alternative-status <ALT_ID> --status testing
# the agent edits and runs the project's relevant checks in its candidate only
sc compare-alternative <ALT_ID>
sc check <INTENT_ID>
sc status
```

Compare reports candidate paths/digests against the **saved intention baseline**, for the declared scopes only. It is not a test suite, a full-repository audit, or a semantic review — inspect the full diff and test results separately, and remember that changes outside declared scopes are invisible to it.

If the shared root changed: re-read it, reconcile the candidate, declare a new revision with `sc declare ... --supersedes <OLD_INTENT_ID>` (same actor), and register the candidate under the new intention. Close out explicitly with `alternative-status ... --status accepted|rejected|abandoned` and `finish <INTENT_ID> --status completed|abandoned`.

## Baseline pitfalls observed in practice

- **Stale shared root.** If the root's HEAD is behind the integration target and lacks files that exist there, baselines record those paths as missing and compare verdicts become noisy for candidates prepared from a newer revision. Use the external-registration route with a fresh worktree, read the compare verdict in that light, and inspect full diffs separately. Declare the honest state rather than quietly re-basing the root underneath other sessions.
- **Silent no-op on the alternatives form.** On the dashboard, submitting the "Preserve a candidate" form with the intention select left empty does nothing — no submission, no validation message, no event. Always confirm the intention is selected (tracked in [issue #59](https://github.com/Moissanite-Labs/synbios/issues/59)).
- **One DB per root.** If two sessions see different records, compare the absolute database paths first.

## Handoff

Before integrating, each session reports: candidate path, intention/alternative IDs, changed files, tests run, remaining conflicts, and the next integration step. Keep databases, tokens and path-bearing reports local; share only concise summaries.
