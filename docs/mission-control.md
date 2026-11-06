# Local mission control

Synbios organizes a goal into work that your agent sessions can pick up, report on and hand back. The Crystal Lattice is the primary view. Start with the outcome, select a piece of work to understand it, and use the decision panel when something needs your judgment.

## Start on your machine

From the Synbios checkout, after installing Python 3.11+, Node.js 22+ and npm:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm --prefix web ci
npm --prefix web run build
python -m synbios start --workspace "/absolute/path/to/exo" --name "Exo"
```

PowerShell activation is `.venv\Scripts\Activate.ps1`. On Windows use a native absolute workspace path. Node is needed to build the interface; the running Python service uses only the standard library.

The launcher validates the folder and built interface, creates a mission for that folder on first use, and prints a loopback URL plus a separate browser credential. Open the URL and enter the credential. Keep the terminal running; Ctrl+C stops the service. Restart with the same command to recover the recorded mission. It does not change source files in the selected folder.

Use `--port 0` to select a free port, or `--port 8766` to select another fixed port. `--db /outside/the/workspace/mission.db` selects a database explicitly. The database and credential cache must remain outside the target source tree.

Default state locations:

| System | State directory |
| --- | --- |
| macOS | `~/Library/Application Support/Synbios` |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/synbios` |
| Windows | `%LOCALAPPDATA%/Synbios` |

`SYNBIOS_STATE_DIR` overrides that directory. Each absolute workspace path gets a `workspaces/<path-hash>/mission.db`; credentials are cached separately under `credentials/<database-path-hash>.json`. The launcher caches the local operator credential so restarting does not require inventing a new identity. Credential files are owner-only on POSIX and use the local user's application-data ACL on Windows. Keep them private; the SQLite store itself retains only token hashes.

An existing database initialized with `synbios init` has no launcher cache. Supply its current human credential through `SYNBIOS_TOKEN` on the first `start --db ...` invocation. Startup authenticates it and then caches it. It never recovers a token from a hash or resets an existing store.

## Read the mission

The five rings retain the designer's stages: **Idea, Shape, Prototype, Build, Ship**. A stage is where a work slice belongs; task status says what is happening to it. Moving a task to Build is not a claim that it passed tests.

- **The crystal and census:** select work, inspect stage membership and recorded completion. Human work uses carbon circles; agent work uses silicon diamonds. Empty positions remain empty.
- **Decision and sources:** understand the selected task, dependencies, evidence and actual pending questions. A candidate differing from its baseline does not create a human bottleneck.
- **Crew:** see identities and their assignments. Registration is not a heartbeat.
- **Live work:** read the latest reported progress and blockers. Reports carry their origin and time; missing usage, cost or compute data stays unavailable.
- **Trace:** follow the recorded changes that produced the current state.

Select a piece and expand **Inspect work and evidence** for **Attach a result**, **Record test evidence** and **Submit for review**. A submitted result appears in the decision panel with review actions. The full record console at `?advanced=1` retains permission administration and export.

## Divide and delegate work

Choose **Edit mission** to replace the startup description with your actual desired outcome. A mission is a project in the API; a work slice is a task. Each slice needs a title, desired result, acceptance criteria and scope. Dependencies refer to other slices in that mission. Put competing approaches in separate slices and candidate folders so both remain inspectable.

Use **Add work slice** to create a slice yourself. To have an agent organize the work, choose **Plan with a coordinator**, name its session and copy the coordinator brief to the local harness of your choice. Enrollment issues a project-scoped coordinator credential. The coordinator can submit a structured plan through `plan.create`; it does not receive human review authority.

Select a slice, choose **Delegate to agent**, name the session and select **Create agent brief**. The one-time handoff includes the task, scope, acceptance criteria, dependencies, local API instructions and that new session's scoped credential. Copy it before closing the dialog. The browser assembles the credential into this handoff locally; the prompt endpoint itself returns no credential and never contains the operator token. Later **Copy task prompt** actions expect the agent to retain its own connection key.

To change the work, choose **Redirect work**. To move it to an existing session, expand **Inspect work and evidence** and select **Assign existing agent**. The former owner's task grants are revoked; its external process still needs to stop using the old assignment. Connected sessions see the change on their next read. Paste a refreshed brief into sessions that are not polling.

Copying a prompt does not launch an agent. Paste it into Codex, Claude Code, Gemini CLI or another harness that can reach this local server. The session must use the scoped credential and report through the API. A cloud-hosted session needs an explicitly provided connection to the machine; being listed in Crew alone does not create one.

Use a separate working copy or Git worktree per implementation. The current main service records coordination and authority; it does not prevent an outside process from writing another process's files. Scope-overlap warnings are requests to reconcile plans, not filesystem locks.

## An agent's return path

The generated brief supplies the exact task and server context. From an environment where Synbios is installed, these are the underlying operations:

```sh
export SYNBIOS_URL='http://127.0.0.1:8765'
export SYNBIOS_TOKEN='the-scoped-session-credential'
python -m synbios state
python -m synbios prompt TASK_ID
python -m synbios coordinator-prompt PROJECT_ID
```

Use `prompt` for a work task, or `coordinator-prompt` for the project coordinator. Fetching a brief does not grant authority; the credential and active grants determine which commands the session can perform.

Delegating or assigning a task already places it in the claimed state. Its agent starts it with `task.transition` to `in_progress`, reports progress or a blocker, then records the candidate and evidence. Use `task.claim` only for an open, unassigned task when the session has a separate claim grant; repeating it after delegation is rejected. `task.report`, reassignment, task edits and decision changes use the task revision from the latest snapshot. If the API rejects a stale revision, reread the task and reconcile the new information before retrying. A stale form keeps its draft; close and reopen it to load the updated work before reapplying your intended change. Do not overwrite a newer report with an old form.

A decision request names the question and available options. Resolving it records the human's choice; it does not accept an artifact, run commands, move files, or merge code. A task submitted for artifact review still requires resolved or withdrawn open questions, current passing test evidence, no current test failure, accepted dependencies and a reviewer other than the author. Redirecting its requirements keeps earlier candidates visible but marks evidence for the earlier contract stale; a new candidate and fresh evidence are required.

For a clean committed Git candidate:

```sh
python -m synbios capture --task TASK_ID --repo /path/to/candidate
python -m synbios export TASK_ID --output contribution.json
python -m synbios verify contribution.json
```

Capture reads the revision and tree digest; it does not run tests. It refuses dirty/untracked content, hidden index entries, submodules and configured filters that could execute during inspection. Artifact and evidence forms are available under **Inspect work and evidence**, with the full record console available for deeper inspection. [Full acceptance and trust rules](trust-model.md).

## Continue from the earlier Exo pilot

There are two distinct stores:

| Store | What it holds | How to use it now |
| --- | --- | --- |
| Main Synbios database from `init`, `demo` or `start` | Projects, tasks, credentials, grants, artifacts, evidence and review | Open through the main service. Existing records remain available; new mission fields receive defaults where needed. |
| `experiments/local-collaboration` coordinator database | Caller-declared intentions, file baselines, isolated alternatives and comparisons | Keep using its own CLI and dashboard when those checks are needed. It is not a main Synbios database. |

The rebuild does not silently import, rename or replace the experiment database. Keep that database and your candidate folders. Represent the pilot's goals and assignments in the new mission, and refer to existing candidates in the task context. Integrating the two stores requires a deliberate migration/adapter with provenance and identifier mapping.

## First acceptance run

1. Start against your Exo checkout and confirm the source working tree is unchanged.
2. Open the mission. Create a small slice with an observable outcome and a narrow scope.
3. Enroll a separate local agent session, copy its brief, and have it report through the API.
4. Confirm its assignment and report appear on the lattice without a manual database edit. Reload and restart; the same records should remain.
5. Ask the agent to raise a real decision with options. Resolve it in the interface and have the agent reread the result.
6. Try a stale task update from a second session. It should be rejected so the sessions must reconcile.
7. Inspect a result with its evidence, submit it for review and complete the independent review from the decision panel.

Report the OS, Python/browser versions, checked-out revision, the action that failed and the visible error. Exclude credentials and private source contents from shared reports. Chromium automation in this repository is separate from native macOS, Windows, Safari and assistive-technology acceptance.

## Common problems

| Symptom | Next action |
| --- | --- |
| Web client not built | Run `npm --prefix web ci` then `npm --prefix web run build` from the checkout. |
| Port already in use | Stop the previous service, choose another `--port`, or use `--port 0`; give agents the printed URL. |
| Existing database requires authentication | Supply its current human `SYNBIOS_TOKEN` once; do not replace the database. |
| Agent appears but no work updates arrive | Confirm that session actually runs, uses its own credential and can reach the printed local URL. Enrollment alone does not connect a harness. |
| Stale task revision | Refresh state and reconcile; retry with the current revision only after checking the intervening change. |
| Scope overlap | Coordinate owners and candidate folders before edits. Scope warnings do not stop filesystem writes. |
| Artifact cannot be submitted | Inspect the latest candidate's tests and dependency status under **Inspect work and evidence**. Old evidence cannot accept a new candidate. |
