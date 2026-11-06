# Local cooperative coordinator prototype

`weave.local.v1` lets independent local harnesses register intentions against an existing folder, inspect overlaps, and observe whether their starting content changed. It requires Python 3.9+ and the standard library, including SQLite. Git is optional. It reads the target folder and writes only its separate SQLite state database and SQLite journal files. This is a runnable experiment, not a deployed daemon or a formal safety proof.

Run from the coordination workspace:

```sh
python -m unittest discover -s prototype -v
python prototype/demo.py
```

The demo uses a disposable temporary folder, invokes each command in an independent CLI process, registers two competing intentions, preserves two alternative records, changes a demo file externally, observes staleness, and withdraws one intention. It removes its temporary files on exit. It does not access Exo source or runtime. On systems where Python is named `python3`, substitute that command.

For an existing project, create the state database in an existing directory **outside** the project:

```sh
python prototype/coordinator.py --db /absolute/state.sqlite init /absolute/existing-project
python prototype/coordinator.py --db /absolute/state.sqlite register-actor codex-session-1
python prototype/coordinator.py --db /absolute/state.sqlite declare --actor codex-session-1 --read src/contracts --write src/module.py
python prototype/coordinator.py --db /absolute/state.sqlite declare --actor another-harness --write src
python prototype/coordinator.py --db /absolute/state.sqlite status
python prototype/coordinator.py --db /absolute/state.sqlite check INTENT_ID
python prototype/coordinator.py --db /absolute/state.sqlite alternative INTENT_ID --label experiment-A --location /external/isolated-candidate
python prototype/coordinator.py --db /absolute/state.sqlite alternative-status ALTERNATIVE_ID --status testing
python prototype/coordinator.py --db /absolute/state.sqlite finish INTENT_ID --status abandoned
```

Use native absolute paths for `--db` and `init ROOT` on Windows; scope arguments remain relative POSIX paths such as `src/module.py`. Replace `INTENT_ID` and `ALTERNATIVE_ID` with IDs from JSON output. All independent harnesses for one folder must use the same database path. A second database does not coordinate with the first.

## Negotiated protocol

Architecture and implementation representatives agreed `weave.local.v1` through agent messages on 2026-11-06. Every successful CLI response is `{ "protocol": "weave.local.v1", "ok": true, "result": ... }`. Runtime failures use `ok: false` and `error`, exiting 1. Successful commands exit 0, including a successful observation that reports conflicts, stale content or unverifiable content; callers must inspect those fields. CLI syntax errors use argparse's normal stderr and exit 2.

| Command | Result and behavior |
| --- | --- |
| `init ROOT` | `workspace`; registers an existing folder, idempotently for the same canonical root |
| `declare --actor A [--read PATH] [--write PATH] [--supersedes ID]` | `intention` and `conflicts`; repeat read/write flags; at least one scope required |
| `check ID` | Current filesystem observation for any retained intention |
| `status` | `workspace`, `actors`, `intentions`, `alternatives`, `conflicts`, `observations`, `events` |
| `register-actor NAME` | Idempotently registers a caller-asserted actor label |
| `finish ID --status completed\|abandoned` | Updated intention; closes an active declaration only |
| `alternative ID --label L --location P [--status S] [--candidate-digest HEX]` | New alternative metadata associated with intention ID |
| `alternative-status ID --status S` | Updated alternative; prior status retained in events |

Intention fields:

```json
{
  "id": "UUID",
  "workspace_id": "UUID",
  "actor": "caller-asserted harness/session identity",
  "revision": 1,
  "supersedes": null,
  "reads": ["src/contracts"],
  "writes": ["src/module.py"],
  "baseline": {
    "src/module.py": {"kind": "file", "sha256": "SHA-256-of-raw-bytes"},
    "src/contracts": {"kind": "missing", "sha256": null}
  },
  "baseline_digest": "SHA-256-of-canonical-JSON-baseline",
  "status": "active",
  "created_at": 0.0
}
```

Workspace fields are `id`, canonical absolute `root`, and `protocol`. Actor names are assertions, with no authentication. Intention statuses are `active`, `completed`, `abandoned`, `superseded`. `completed` says that an actor closed its declaration; it does not mean code exists, tests passed, approval was granted, or integration happened. A new declaration with `--supersedes` captures a new baseline, increments revision, and atomically retires an active declaration with the same asserted actor. Its old baseline and events remain available. Changed scope cannot silently overwrite previous intent history.

Actor registry records contain `name`, `registered_at`, and `registration` (`explicit` or `inferred-from-intention`). Explicit registrations are persisted as `actor.registered` events. Status also includes actors discovered in retained intentions. Registration does not launch or connect a harness and supplies no liveness, session, capability or authentication guarantee. This additive field was negotiated with the dashboard representative for the local UI.

Baseline entries are `file`, `directory`, or `missing`. Files hash raw bytes without relying on timestamp or length. Directories hash the sorted immediate child names as canonical JSON, and every descendant is separately observed. Thus new files, deletions and changed contents under a directory scope are detectable. A nonexistent exact scope has an explicit `missing` entry with null hash. Directory scans include hidden files, build outputs and Git metadata if those are under the scope; use narrow scopes for large trees. Canonical JSON uses sorted keys, compact separators and Python's default ASCII escaping, encoded UTF-8 before SHA-256.

Scopes use normalized relative POSIX paths, with `.` covering the whole root. Absolute paths, `..`, backslashes and colons are rejected. Existing symlinks in a scope or in any ancestor below the registered root are rejected. Existing special files are rejected. An initial root alias is resolved to a canonical directory when registered.

Two active declarations conflict when equal or ancestor/descendant scopes overlap and at least one writes. Read/read pairs are compatible. Overlap is conservative even for nonexistent paths. Comparison uses Unicode NFC and case folding to reduce common cross-platform alias misses, potentially adding false conflicts on case-sensitive filesystems. `src` does not overlap `src2`. Reports contain `left_intent`, `right_intent`, `left_path`, `right_path`, and `kind`: `write/write`, `write/read`, or `read/write`. Direction refers to the left and right declarations. A pair may have multiple hazard entries. Self-overlap within one intention is not reported.

Declarations with conflicts are retained; advisory conflict reporting does not forbid isolated experiments. This prototype cannot ensure a writer waits or chooses an isolated copy. Read/write entries expose dependencies, but the prototype does not schedule work or resolve them.

Observations contain `intent_id`, `state`, `changed_paths`, `observed_digest`, `observed_at`. State is `current` or `stale`; if observation fails, state is `unverifiable` and `error` replaces the latter four fields. Replacing a scoped file with a symlink therefore does not falsely report current. Status observes active intentions; `check` can observe historical ones.

Alternative fields are `id`, `intent_id`, `label`, `location`, `status`, optional-value `candidate_digest`, and `digest_source`. Status is `proposed`, `testing`, `accepted`, or `rejected`. Location is an opaque caller-supplied string; no copy, branch, worktree, checkout, sandbox or artifact is created or validated. An optional lowercase SHA-256 digest is **caller-asserted**, with `digest_source: "caller-asserted"`; otherwise both fields are null. `accepted` is a reporter's comparison label, never human approval or permission to integrate. Rejected alternatives and their metadata remain retained, but external candidate files must be preserved by the caller. There is no exact-artifact approval support.

Events contain monotonic database `sequence`, wall-clock `time`, `kind`, and `data`. Event kinds are `workspace.initialized`, `actor.registered`, `intention.declared`, `intention.superseded`, `intention.completed`, `intention.abandoned`, `alternative.registered`, `alternative.status`. Registration events retain the original full record; transition events identify the affected ID and transition. Event timestamps depend on the local clock; sequence supplies local ordering.

## Persistence and limits

Each mutation and its events commit in one SQLite transaction. Declaration uses `BEGIN IMMEDIATE` so concurrent registrations serialize their conflict inspection and cannot lose each other's records. SQLite's default rollback journal and 30-second busy timeout are used; lock exhaustion reports an error. Status reads a consistent database snapshot before observing the filesystem. Baselines are captured before the declaration transaction, so they can already be stale when registered. Database storage has no pruning or schema migration support in v1.

This is cooperative local coordination, not filesystem enforcement. Agents can ignore declarations, omit reads, lie about identity, alter the database, use another database or edit source without registering. Events are ordinary database records, not signatures or tamper-proof evidence. A path prefix check does not detect all filesystem aliases, such as hard links, Windows short names or mount aliases. Symlink checks have filesystem check/open races; hostile concurrent replacement is outside the trust model. The coordinator is not a security boundary.

Filesystem scans are sequential, not atomic snapshots. A scan can mix file versions during concurrent edits; replacing a root directory at the same path may also invalidate identity assumptions. Mode/ownership metadata, extended attributes and permissions are not hashed. Observations cannot prove that bytes stayed unchanged after the check. OS locks, intercepting all writes, isolated materialized workspaces, atomic apply, approvals and merge conflict resolution are future work. This prototype does not write target source, auto-merge or promote alternatives.

The storage design assumes SQLite locking works on a local disk. Multi-host/network filesystem deployment, crash recovery under power failure, Mac runtime integration, heterogeneous commercial harness integrations and Windows/macOS behavior have not been tested here. The code uses portable stdlib APIs; execution evidence is Linux with Python 3.12.14. Source size/performance bounds, cryptographic identity, and authenticated remote services are not implemented.

## Verification evidence

`python -m unittest discover -s prototype -v` exercises six independent spawned processes, released together by a barrier, each registering a write to the same file. It verifies six durable intentions, six matching declaration events, all fifteen pairwise conflicts, monotonically increasing conflict visibility across transactions, and an unchanged target snapshot. Other tests cover byte changes with preserved timestamp/size, directory additions/deletions, missing-path creation, directory/read-write conflicts, case/Unicode comparison, supersession and failed-operation rollback, alternative history, unsafe scopes/database placement, symlinks, and JSON CLI responses. These are executable tests, not model checking or formal proofs.

`python prototype/demo.py` exercises the complete local CLI flow using temporary files. The demo intentionally acts as an external editor to make a baseline stale. Its outputs report two initial hazards, current then stale content, two retained alternatives and seven events.
