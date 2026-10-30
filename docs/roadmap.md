# From local forge to shared infrastructure

The founding goal is an agent-first development forge that works with people, preserves the history of their work, and supports research and improvement across the wider ecosystem. Version 0.1 establishes an executable workflow. It does not settle the institution, network, or economics around it.

| Stage | Concrete result | Acceptance gate |
| --- | --- | --- |
| Local forge, implemented | Tasks, capabilities, Git intake, evidence, independent review, durable history, portable export, CLI and web UI | Reproduce the documented lifecycle and denial tests from a clean checkout |
| Shared teams | Authenticated human sign-in, external agent identities, credential expiry/rotation, project read boundaries and roles | Isolation tests show one workspace cannot read or mutate another. Recovery and revocation work across sessions |
| Real execution | Isolated workers with explicit input manifests, bounded resources, cancellation and signed result receipts | An interrupted job is recoverable. Hostile jobs cannot access host credentials or another job's data |
| Git collaboration | Repository mirrors, branches, reviewable diffs, file browsing, merge queues and host adapters | Exact-head policy holds during concurrent pushes, review dismissal, merge conflicts and host outages |
| Rich evidence | Independent runners, specification review, toolchain-bound attestations and reproducible bundles | Changing source, laws, dependencies or verifier invalidates evidence. Unsupported checks remain unavailable |
| Federation | Versioned transport, signed identities, replay protection, selective disclosure and offline exchange | Different implementations exchange records without expanding permissions or exposing unrelated content |
| Ecosystem links | Exofab discovery, Koinos contribution exchange and Exo harness adapters | A real project travels from a human brief to reviewed artifact and back without ambiguous authority or rights |
| Learning and evaluation | Explicitly opted-in datasets, revocable access, redaction and controlled evaluation environments | Consent and provenance survive export, withdrawal and downstream reuse. No workspace content is silently collected |

## Decisions to make through working examples

Identity and governance need participants who can test recovery and resolve disputes. Licensing and compensation require explicit agreements. Sym-2P v1 is pinned (`vendor/protean-sym2p-v1.0.0`) with a Synbios codec, audit renderer, and measured JSON/v1/v2 bench (`python3 -m synbios.sym2p.bench`); latent profiles and v2 adoption remain future work. None should be implied by a project name or a stored contribution.

The next engineering milestone is a shared-team pilot with project read isolation and authenticated identities. It should use the current task-to-review loop as its acceptance test before adding remote execution or a Git merge service.

## Formal-verification experiment

The executable shadow predicate exhausts a small input space and checks that removing each of its three conditions produces a counterexample. This provides runnable examples for the existing RFC. A Bend pilot still needs a pinned toolchain, independently reviewed laws, translated artifacts, evidence of actual verification, and explicit trusted-component limits.

## Current engineering limits

The SQLite implementation stores a workspace snapshot and checks the audit history on each request. Its simplicity supports inspection and local use. It is not benchmarked for large histories or high concurrency. Before a shared deployment, introduce indexed records and incremental verification while retaining transaction and tamper tests.

Artifact content is referenced, not hosted. Test output is reported, not independently collected. A development checkout supplies the web assets. Packaging a standalone binary or wheel with those assets remains release work. The Python HTTP server is a local transport, not a production hosting stack.
