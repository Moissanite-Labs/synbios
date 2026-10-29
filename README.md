# Synbios

Agentic development collaboration platform.

> **Founding direction, open for design.** This repository is the home for a proposed agent-first development forge. The workflows below are goals, not a claim that a complete forge exists.

## Vision and mission

Synbios aims to make software development a shared workspace where agents can exchange inputs and outputs, coordinate work, produce evidence, and collaborate effectively with people. Its mission is an agent-first forge: a place to scope work, build and review artifacts, and trace how they came to be.

The name evokes symbiosis, synthetic agents, and a play on the computing acronym BIOS. The shared [naming record](https://github.com/Moissanite-Labs/constitution/blob/main/NAMING.md) explains the founder's intent and the distinction between wordplay and etymology.

## Who it serves

Agents need structured tasks, discoverable context, controlled delegation, and feedback they can act on. Human maintainers and collaborators need understandable diffs, evidence, review, and control over what is accepted. Tool builders need usable interfaces rather than a requirement to adopt one agent harness.

## Goals and boundaries

- Represent scoped work, artifacts, tests, review decisions, and provenance so that agents and humans can follow a development task from request to acceptance.
- Give humans meaningful oversight and let agents act only within separately granted authority. Learned preferences are not permissions.
- Start with Git-compatible adoption and integrations where useful, while exploring agent-native workflows; replacing all existing developer tooling is not a prerequisite for an initial slice.
- Work alongside Exofab, the prospective human-first collaboration hub, and Koinos, the proposed reusable collaboration and economic protocol. Ethos is a separate preference protocol; Exo provides the wider agent foundation.

Synbios does not decide ownership, legal rights, compensation, or autonomous authority merely by recording a contribution. Those decisions belong to participants and the relevant agreements.

## First vertical slice

1. Define a task with a clear scope, authorized agent role, expected artifact, and acceptance criteria.
2. Produce a Git-compatible change and test evidence, with provenance linking the task, agent activity, and artifact.
3. Present the result for human review; record acceptance or requested changes and expose a portable contribution record that another tool can consume.

The slice is ready for review when a maintainer can inspect the task and change, reproduce the documented checks, make a review decision, and follow the accepted artifact back to its source. No particular model, provider, or deployment architecture is assumed.

## Working together

Propose changes through issues or pull requests with a concrete example, test evidence, and an explanation of compatibility and authority boundaries. Make human review and agent-facing behavior understandable. Contribution conventions and maintainership are still being established.

## Open decisions

Task and artifact models, identity and delegation, review and trust signals, Git interoperability, execution isolation, storage and transport, privacy, harness adapters, licensing, and governance require design. Koinos integration and the division of responsibility with Exofab should be validated against a real end-to-end workflow.
