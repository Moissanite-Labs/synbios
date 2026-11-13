---
name: continuous-synthesis
description: Preserve software capabilities and evolve them with affected peers when substantial implementation, interface, or dependency changes need durable purpose, negotiated adaptation, and composition evidence.
---

# Continuous synthesis

Treat a meaningful capability as a durable responsibility to a human purpose. Its identity survives file moves, rewrites, dependencies, and agent sessions. The code need not be conscious or self-executing: an agent acts as its steward using observable signals, explicit contracts, and evidence.

Apply this practice inside the authorized task. It grants no additional permissions and requires no background service, agent per file, or separate ceremony for a small edit.

## Locate purpose and responsibility

Look in repository instructions, capability records, interfaces, and existing tests before creating a record. Identify the outcome, what must continue to hold, failure signals, affected peers, and current evidence. A capability is a behavior or responsibility, not necessarily a module. Reuse an existing issue, design record, or task artifact when it can preserve this information durably.

Use a stable capability ID independent of its paths. Record current implementation links separately. A redesign updates those links; a split or merger records successors and the responsibilities each inherits. Keep previous evidence and uncertainty discoverable. Humans set purpose and authority; an agent may improve the means within the task's scope, and surfaces purpose conflicts for human direction.

## Adapt with peers

Follow the useful parts of this loop at the scale of the change:

1. **Observe:** identify a concrete mismatch, failure, dependency change, or supported opportunity. Distinguish observation from a suspected explanation.
2. **Propose:** describe the smallest adaptation, the responsibility it preserves, affected contracts, and evidence that could disprove its benefit.
3. **Respond:** ask the affected peer or its steward to accept, reject, or counterpropose from its own responsibilities when the contract changes. Preserve the response and its provenance. If no peer can respond, state that uncertainty; simulated roles are not independent participation.
4. **Compose:** exercise the changed parts together. Component checks alone do not establish that peers interoperate. Match checks to the change, including relevant failure cases. A new revision can invalidate earlier responses and evidence.
5. **Retain:** put the useful lesson and next action in the capability's canonical record. Where appropriate, encode it in a test, interface, or existing procedure. Keep a rejected or falsified proposal as such; do not accumulate standing rules for every observation.

A peer response concerns a contract; it is not permission to merge, deploy, publish, or act outside the current task. Record unresolved disagreement instead of asserting consensus. Stop retries when they offer no new evidence.

## Leave continuity

Keep enough durable state for a successor to recover: stable ID, human purpose, responsibilities, implementation links, peers and mutual obligations, current observation/proposal, peer response, composition evidence, retained lesson, and next action. State unknowns and evidence limits. Existing project conventions determine the format.

Distinguish proposed adaptation, local implementation, tested composition, actual integration, and observed live behavior. A ledger status, installed instruction, or actor registration proves only what was recorded; it does not launch a harness, establish liveness, or verify an outcome.

For the optional Synbios local coordinator and capability ledger, read [references/local-coordinator.md](references/local-coordinator.md). The general practice works without that prototype.
