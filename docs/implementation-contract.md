# Forge foundation and mission contract

This local-first reference implementation turns Synbios's task → artifact → evidence → human review → portable record workflow into running software. It does not grant remote execution, Git merge, economic rights, or training-data consent.

## Mission-control extension

[Local mission control](mission-control.md) is the user-facing workflow; [the pinned Crystal Lattice design](design/crystal-lattice.md) defines its visual composition. The same authenticated store now supports mission outcomes, stages, plans, assignments, reports and decisions. Existing main-store records remain available; missing mission fields are defaulted in the read model. The separate local-collaboration experiment database is not imported.

New commands are enumerated in the authenticated `/api/schema`:

| Command | Authority and behavior |
| --- | --- |
| `project.update` | Human; `project_id`, `expected_revision`, optional `name` and `description`. Workspace location remains fixed. |
| `coordinator.enroll` | Human; `project_id`, `name`. Returns a new agent's one-time token and a project coordinator grant. |
| `coordinator.revoke` | Human; `grant_id`. Ends coordination authority; independently issued worker grants remain. |
| `plan.create` | Human or project coordinator; `project_id`, `tasks`. Each slice has a unique local `key`, task fields and dependencies on local keys or existing same-project task IDs. Atomic, bounded to 100 slices, acyclic. |
| `task.assign` | Human or project coordinator; `task_id`, `principal_id`, `expected_revision`. Revokes outgoing owner's task grants and grants/assigns incoming owner. |
| `task.delegate` | Human or project coordinator; `task_id`, `name`, `expected_revision`. Creates and assigns a worker; returns its one-time credential. |
| `task.update` | Human or project coordinator; `task_id`, `expected_revision`, changed task fields. Changes to scope/criteria/description/dependencies invalidate acceptance against the previous contract. |
| `task.report` | Human or task worker; `task_id`, `expected_revision`, `summary`, optional integer `progress` (0–100) and `blocker`. Attributed report only. |
| `decision.create` | Human or task worker; `task_id`, `expected_revision`, `title`, `question`, 2–8 distinct `options`. Creates a real pending question. |
| `decision.resolve` | Human; `task_id`, `decision_id`, `expected_revision`, recorded `choice`, optional `note`. Records the choice; does not approve an artifact. |
| `decision.withdraw` | Requester with work authority or human; task/decision IDs, `expected_revision`, optional `note`. Withdraws an open question. |

Projects add `workspace` and `revision`. Tasks add `stage` (`idea`, `shape`, `prototype`, `build`, `ship`), `candidate_path`, `revision`, `contract_revision`, `assignment_revision`, `reports` and `decisions`. Candidate paths are metadata, not created or isolated folders. Derived snapshot fields include blockers, conservative `scope_overlaps` and resource allocation. Runtime usage/cost/compute are explicitly unavailable. New task mutations use compare-and-swap revision checks and return 409 for stale input. Accepted task immutability still applies.

`GET /api/tasks/{id}/prompt` and `GET /api/projects/{id}/coordinator-prompt` return portable, credential-free brief text. Scoped credentials are issued separately. CLI equivalents are `prompt TASK_ID` and `coordinator-prompt PROJECT_ID`. `command ACTION --data-file payload.json` supports portable JSON input without shell quoting.

`start --workspace PATH [--db PATH] [--name NAME] [--port PORT]` validates the built client, creates or reconnects to the local mission, and serves it. It stores a private operator credential outside the workspace for restart; unlike the hashed SQLite credential record, this local launcher cache contains the secret. Existing databases without a cache need a current human `SYNBIOS_TOKEN`. See [state locations and restart behavior](mission-control.md#start-on-your-machine).

The foundation contract below remains the authority for artifact evidence, independent review, export and the existing CLI. Where it lists only the original fields, the mission additions above extend them.

## Runtime

Python 3.11+ standard library, SQLite persistence, React/TypeScript web client. One local server binds loopback by default. Bearer credentials identify principals on every API request; role and scope are never taken from request body. Fresh stores bootstrap via CLI only. No network bootstrap endpoint. Enrollment tokens are shown once and stored hashed in SQLite; the opt-in local `start` launcher also keeps its operator credential in a private restart cache. A local operator is a trusted administrator, not a simulated remote identity provider.

## Shared wire format

Snapshot returned by GET /api/state:
`{version:1, actor:{id,name,kind}, projects:[], tasks:[], principals:[], grants:[], events:[], integrity:{valid:boolean,event_count:number}, metrics:{}}`

Project: `{id,name,description,repository,created_at}`.
Task: `{id,project_id,title,description,criteria:string[],scope:string[],status,priority,assignee_id:null|string,dependencies:string[],created_by,created_at,updated_at,artifacts:[],evidence:[],reviews:[]}`.
Statuses: `open`, `claimed`, `in_progress`, `in_review`, `changes_requested`, `accepted`, `cancelled`.
Artifact: `{id,task_id,title,kind:'git_commit'|'document',revision,digest,uri,summary,created_by,created_at}`. Git revisions must be full 40/64 hex; digest SHA-256. Document revision is SHA-256. Never dereference user URLs.
Evidence: `{id,task_id,artifact_id,artifact_digest,revision,kind:'test'|'proof'|'analysis',status:'passed'|'failed'|'unavailable',command,summary,tool,tool_version,created_by,created_at,assumptions:string[]}`. Proof is shadow evidence, not platform-verified truth. Derive `stale` if artifact binding is no longer current. Evidence on an older artifact is not current.
Review: `{id,task_id,artifact_id,revision,decision:'approved'|'changes_requested',comment,created_by,created_at}`.
Principal: `{id,name,kind:'human'|'agent',created_at,active}`; no credentials in snapshot.
Grant: `{id,principal_id,task_id,capabilities:string[],created_by,created_at,revoked_at:null|string}`.
Event: `{seq,id,type,actor_id,task_id:null|string,created_at,payload,previous_hash,hash}`. SHA-256 chained canonical JSON. Integrity is local tamper detection, not signature/authenticity or completeness after whole-store replacement.

## Store Python interface (domain owner)

`Store(path)` opens/initializes SQLite; `bootstrap(name='Maintainer') -> {token,principal}` refuses a second bootstrap. `authenticate(token) -> principal`; `snapshot(token) -> above`; `command(token,action,payload) -> created/changed entity`; `export(token,task_id) -> portable JSON bundle`; `verify_integrity() -> {valid,event_count,...}`. `verify_bundle(bundle) -> {valid,errors:[...]}` exported from synbios.store. Domain errors expose `status` (400/401/403/404/409) and message; API serializes `{error:message}`.

Commands POST /api/commands/{action} JSON:
- `project.create`: name, description, repository (human)
- `principal.create`: name, kind -> `{principal,token}` (human; credential shown once)
- `principal.revoke`: principal_id (human; revokes credential/read access and actions, refuses self or last active human)
- `grant.create`: principal_id, task_id, capabilities (human); supported `claim`, `work`, `artifact`, `evidence`, `submit`
- `grant.revoke`: grant_id (human)
- `task.create`: project_id,title,description,criteria (nonempty),scope (nonempty),priority ('low'|'normal'|'high'),dependencies,stage,candidate_path (human; project coordinators use `plan.create`)
- `task.claim`: task_id (human or task-scoped claim)
- `task.transition`: task_id,status (`in_progress`,`in_review`,`cancelled`,`open`); agent must hold work or submit as appropriate. Submission needs current artifact, passing current test evidence, no current failed test evidence, and all dependencies accepted. Human can cancel/reopen; accepted tasks immutable.
- `artifact.add`: task_id,title,kind,revision,digest,uri,summary (human or artifact grant). Adding new artifact invalidates old approval/evidence for current candidate; cannot modify accepted task.
- `evidence.add`: task_id,artifact_id,artifact_digest,revision,kind,status,command,summary,tool,tool_version,assumptions (human or evidence grant); binding must match artifact, task mutable.
- `review.create`: task_id,artifact_id,revision,decision,comment (human only, not current artifact author). Approval checks exact current candidate, current evidence and dependencies atomically and moves task to accepted. Changes requested moves status accordingly. No Git merge performed.

API: GET /api/health (no state), GET /api/state, GET /api/tasks/{id}/export, POST /api/commands/{action}; all but health/static authenticate. POST /api/bundles/verify verifies supplied JSON with authentication. Error status codes preserve domain status. Same-origin only; no permissive CORS; validate Host and Origin, bounded bodies, loopback default. Static SPA served from web/dist, no filesystem traversal. GET /api/events may return snapshot events; no SSE needed for initial reference. Web dev proxies /api to 127.0.0.1:8765. Tokens sessionStorage only, no preloaded credentials in web code.

## CLI and demonstration (transport owner)

`python -m synbios init --db PATH --name NAME`, `serve --db PATH --port 8765`, `demo --db PATH` (new DB only, synthetic records clearly labeled; separate author and reviewer), `state`, `command ACTION --data JSON`, `export TASK --output PATH`, `verify BUNDLE`, `capture --task TASK --repo PATH` (read-only git intake via subprocess argument vectors; dirty tree refused; no shell). Authenticated clients use `SYNBIOS_TOKEN`, default URL http://127.0.0.1:8765. Capture uses full HEAD, canonical recursive Git tree manifest and its SHA-256 digest, no automatic test execution. Demo returns local operator credential and seeds project/tasks/review/evidence through normal commands; synthetic fixture evidence explicitly labeled. GUI seed is optional explicit CLI action, never production-looking fabricated activity.

## Acceptance

Run clean install/build; domain tests authorization, stale evidence/review, revocation, dependency/cycle and transitions, persistence and integrity tampering; HTTP tests auth/origin/path/body guards; CLI Git intake and export verification; browser test real create/claim/artifact/evidence/review cycle plus narrow/mobile states. No remote deploy or auto-merge. Document implemented features and full-vision roadmap separately.

Discovery: GET /.well-known/synbios.json exposes only public protocol metadata. GET /api/schema exposes the authenticated OpenAPI contract. Commands reject unknown payload fields. Git capture does not load system or global Git configuration, and it refuses clean/process filters that remain configured, plus submodules, because inspection can execute their programs.

New database files are owner-readable/writable only; existing file modes are preserved and symlink DB paths refused. The CLI accepts loopback HTTP origins only and refuses redirects and proxy routing. Bundle verification checks structure and supplied bindings, not omitted dependency acceptance or externally authenticated identity.
