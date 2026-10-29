# Forge foundation contract

This local-first reference implementation turns Synbios's task → artifact → evidence → human review → portable record workflow into running software. It does not grant remote execution, Git merge, economic rights, or training-data consent.

## Runtime

Python 3.11+ standard library, SQLite persistence, React/TypeScript web client. One local server binds loopback by default. Bearer credentials identify principals on every API request; role and scope are never taken from request body. Fresh stores bootstrap via CLI only. No network bootstrap endpoint. Tokens are shown once and stored hashed. A local operator is a trusted administrator, not a simulated remote identity provider.

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
- `task.create`: project_id,title,description,criteria (nonempty),scope (nonempty),priority ('low'|'normal'|'high'),dependencies (human)
- `task.claim`: task_id (human or task-scoped claim)
- `task.transition`: task_id,status (`in_progress`,`in_review`,`cancelled`,`open`); agent must hold work or submit as appropriate. Submission needs current artifact, passing current test evidence, no current failed test evidence, and all dependencies accepted. Human can cancel/reopen; accepted tasks immutable.
- `artifact.add`: task_id,title,kind,revision,digest,uri,summary (human or artifact grant). Adding new artifact invalidates old approval/evidence for current candidate; cannot modify accepted task.
- `evidence.add`: task_id,artifact_id,artifact_digest,revision,kind,status,command,summary,tool,tool_version,assumptions (human or evidence grant); binding must match artifact, task mutable.
- `review.create`: task_id,artifact_id,revision,decision,comment (human only, not current artifact author). Approval checks exact current candidate, current evidence and dependencies atomically and moves task to accepted. Changes requested moves status accordingly. No Git merge performed.

API: GET /api/health (no state), GET /api/state, GET /api/tasks/{id}/export, POST /api/commands/{action}; all but health/static authenticate. POST /api/bundles/verify verifies supplied JSON with authentication. Error status codes preserve domain status. Same-origin only; no permissive CORS; validate Host and Origin, bounded bodies, loopback default. Static SPA served from web/dist, no filesystem traversal. GET /api/events may return snapshot events; no SSE needed for initial reference. Web dev proxies /api to 127.0.0.1:8765. Tokens sessionStorage only, no preloaded credentials in web code.

## CLI and demonstration (transport owner)

`python -m synbios init --db PATH --name NAME`, `serve --db PATH --port 8765`, `demo --db PATH` (new DB only, synthetic records clearly labeled; separate author and reviewer), `state`, `command ACTION --data JSON`, `export TASK --output PATH`, `verify BUNDLE`, `capture --task TASK --repo PATH` (read-only git intake via subprocess argument vectors; dirty tree refused; no shell). Authenticated clients use `SYNBIOS_TOKEN`, default URL http://127.0.0.1:8765. Capture uses full HEAD, git diff parent..HEAD and SHA-256 digest, no automatic test execution. Demo returns local operator credential and seeds project/tasks/review/evidence through normal commands; synthetic fixture evidence explicitly labeled. GUI seed is optional explicit CLI action, never production-looking fabricated activity.

## Acceptance

Run clean install/build; domain tests authorization, stale evidence/review, revocation, dependency/cycle and transitions, persistence and integrity tampering; HTTP tests auth/origin/path/body guards; CLI Git intake and export verification; browser test real create/claim/artifact/evidence/review cycle plus narrow/mobile states. No remote deploy or auto-merge. Document implemented features and full-vision roadmap separately.

Discovery: GET /.well-known/synbios.json exposes only public protocol metadata. GET /api/schema exposes the authenticated OpenAPI contract. Commands reject unknown payload fields. Git capture refuses configured clean/process filters and submodules because inspection can execute their programs.

New database files are owner-readable/writable only; existing file modes are preserved and symlink DB paths refused. The CLI accepts loopback HTTP origins only and refuses redirects and proxy routing. Bundle verification checks structure and supplied bindings, not omitted dependency acceptance or externally authenticated identity.
