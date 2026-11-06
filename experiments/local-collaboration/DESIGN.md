# Design direction and integration boundaries

The immediate goal is asynchronous collaboration by heterogeneous agent sessions over existing folders on macOS, Windows and Linux. Exo core and desktop are the proposed first real test subject. Codebase-specific contracts describe how parts fit together; their boundaries can evolve rather than becoming permanent file partitions.

Persistent representative profiles retain each part's knowledge and obligations. Temporary specialist teams perform bounded work. Affected representatives deliberate collectively on shared contracts and use reversible experiments when alternatives remain unresolved. The human view presents product goals, progress, architecture/design choices and comparison evidence without requiring routine code inspection.

## Current experiment

The versioned weave.local.v1 contract records workspace identity, caller-asserted actors, immutable intention revisions, read/write scopes, raw-content baselines, alternatives and events. SQLite serializes metadata mutations and their events. Read/read overlap is compatible; read/write and write/write overlaps are reported. Alternatives can proceed independently, but metadata labels do not authorize integration or demonstrate candidate isolation.

The loopback backend and dashboard reuse the coordinator's actual database. They do not establish authenticated harness or human identities. Baselines are sequential observations and can race unmanaged edits. Changes after observation invalidate assumptions; the experiment has no source-apply operation that could enforce a final compare-and-swap. Full histories and folder scans are unbounded in this prototype.

Two external harness adapters live under `harness/`: **exo-core** (pinned Exo from `main`, `exo serve` with the echo engine and an isolated `EXO_HOME`) and **cli-subprocess** (a cooperative Python worker in a second OS process under `.lc-cli-work/` inside the workspace). They coordinate with the same coordinator and document reconnect tokens, stop, crash-ambiguity buckets, and scope evidence as JSON next to disposable workspaces in automated tests. They wrap execution surfaces; they do not port Exo swarm plan validators or executors from open PRs.

## Repository ownership

- Synbios is the proposed home for the build-collaboration feature and its task/artifact/evidence integration. Its current human acceptance and permission rules remain unchanged.
- [Exo](https://github.com/Moissanite-Labs/exo) owns shared runtime, memory, protocol and harness integration. Its [repository workflow](https://github.com/Moissanite-Labs/exo/blob/main/docs/REPOSITORY-WORKFLOW.md) assigns native shell/packaging to exo-desktop and treats exo-cli as a fork snapshot pending reviewed extraction.
- Existing Swarm work [1189](https://github.com/Moissanite-Labs/exo/pull/1189), [1190](https://github.com/Moissanite-Labs/exo/pull/1190) and [1191](https://github.com/Moissanite-Labs/exo/pull/1191) should inform adapters rather than be duplicated. Their open-PR reports do not establish main or installed behavior.
- Exoframe supplies [Crystal Lattice visual provenance](https://github.com/Moissanite-Labs/exoframe/blob/main/docs/design/public-intake/SPEC.md). It is not the execution backend. Exofab remains the broader human-agent creation hub.

Final placement of a reusable coordinator package requires an explicit Synbios/Exo interface agreement. Keeping this code under experiments does not settle that packaging decision.

## Next evidence

1. Run the portable suite and actual browser workflow on macOS and Windows, recording platform-specific path, case, Unicode and symlink/reparse behavior.
2. Inventory the actual Exo/desktop revisions and existing owners without disturbing running applications or uncommitted changes.
3. Connect two different real harnesses through explicit adapters, then test reconnect, stop, crash ambiguity and scoped execution.
4. Add materialized candidate isolation, versioned component contracts and exact-artifact comparison/decision evidence before any source application.
5. Integrate with Synbios acceptance and Exo execution under their existing authority boundaries.

Formal verification or verifiability from circuits through interfaces remains a governing research ambition. Tests, signatures, model checks and proofs establish different claims and must remain labeled by scope and assumptions. Synbios's [proof-evidence RFC](../../docs/proof-evidence-rfc.md) remains a proposal; this experiment does not implement its verifier or alter merge policy. Learned communication, weight programming and FPGA co-design are connected research tracks, not prerequisites for the practical folder product. Existing [ABIOS state-transfer work](https://github.com/Moissanite-Labs/abios/issues/42) provides a research anchor.
