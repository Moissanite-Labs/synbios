# Trust and authority

Synbios 0.1 is a local reference forge. The operating-system user and human administrators are trusted. It is not a public, multi-tenant service.

## Credentials and permissions

A fresh store is initialized through the local CLI. The API has no bootstrap route. It accepts a bearer token, hashes it, and finds the active principal for that credential. A request cannot choose its own actor or role.

Human principals are administrators. They create projects, tasks, principals, and grants. Agents can read the whole workspace, including its history, but need a grant for each task action. A grant names a task and a subset of `claim`, `work`, `artifact`, `evidence`, and `submit`. Revoking one grant leaves other grants in force.

Revoking a principal removes its credentials and all workspace access. Self-revocation and removal of the last human administrator are refused.

Task scope is a statement of permitted work. Synbios does not inspect filesystem access or control an agent's external tools. A revoked grant blocks subsequent forge mutations. It does not terminate a process running elsewhere. The forge never infers permission to execute code, merge a branch, deploy, spend money, or reuse training data.

## Acceptance

Starting work requires an explicit claim. A work-only grant cannot take an open task out of the claim queue.

Submission and approval check the latest artifact. Its test evidence must include a passing record and no failed record. A later passing record does not erase a failure. Attach a new candidate and fresh evidence for a rerun. Prior evidence stays visible as stale.

All task dependencies must be accepted. Dependencies are selected from existing tasks at creation and cannot be edited, so the dependency graph cannot acquire a cycle. Accepted tasks cannot be reopened or changed. Create a successor task to revise accepted work.

Only a human principal other than the latest artifact's author can review it. Approval binds the exact artifact ID and full revision. It rechecks evidence and dependencies in the same transaction that records the decision. This separates locally declared identities. It does not prove that two accounts belong to different people.

Evidence is an authenticated participant's report. The forge neither runs the command nor establishes its result independently. A proof record has no special acceptance authority and is labeled as a shadow claim. A test record is still required.

## Stored history and portable records

New database files are created with owner-only permissions. Existing file permissions remain under the operator's control, and symlink database paths are refused.

Each mutation writes state and an event atomically to SQLite. Events form a SHA-256 chain and the latest event commits to the saved state. Reads and mutations check this relationship. A changed row or broken chain causes refusal instead of a valid workspace view.

An attacker who can rewrite the database can recompute the chain or replace the entire store. There are no external witnesses, signatures, rollback counters, or durability claims across machine failure. Back up the closed database using normal operating-system practices.

A contribution bundle includes one task, its project, involved public identities, its events, and hash commitments to the omitted events. No raw credentials, credential hashes, unrelated task text, or unrelated grant payloads are exported. Task IDs and the length of the workspace history remain visible in the record.

The verifier checks the bundle digest, event commitments, artifact and evidence bindings, and recorded human review. It cannot authenticate the omitted events, establish completeness, verify dependent tasks' acceptance, or prove that a command ran. It never imports records, grants authority, or merges code.

## HTTP and browser boundary

The server accepts loopback bindings only. The CLI accepts only loopback HTTP origins, refuses redirects, and ignores proxy environment variables when sending credentials.

Host and Origin checks refuse ordinary cross-origin access and DNS rebinding through a foreign Host. Requests have bounded JSON bodies. Static paths are resolved within the built web directory. Responses disable caching and set a content security policy.

The browser stores the credential in session storage. Signing out removes it. A compromised local browser session or operating-system account is outside this boundary. Do not use a public reverse proxy to bypass the loopback restriction.

## Git intake

Git capture is an explicit CLI action against a local repository. It reads the full commit ID and hashes the raw bytes of `git ls-tree -r -z --full-tree REVISION`. This canonical manifest contains tracked paths, modes, types, and full object IDs. Diff display settings and local object replacements cannot change the digest. Optional index writes are disabled.

No test command, URL, hook, external diff, or text conversion is intentionally executed.

Capture refuses dirty or untracked content, assume-unchanged or skip-worktree index entries, configured clean/process filters, and submodules. This includes environments with globally configured Git LFS filters. These restrictions prevent ordinary Git inspection from invoking repository-controlled programs.

Capture checks the working tree and HEAD again before returning. It is a best-effort local consistency check, not a filesystem lock or sandbox.
