# Continuous synthesis

Software can retain a responsibility even when its current implementation is replaced. Continuous synthesis makes that responsibility explicit: a human sets a purpose, an agent stewards a capability, and affected peers respond to proposed adaptations using evidence from their own obligations.

This gives code functional agency through its stewards and interfaces. It makes no claim that code is conscious, that a record can act on its own, or that unattended adaptation is running. A capability might be durable handoff delivery, identity verification, or reproducible export. It can span several modules, and one module can serve several capabilities. Giving every file an agent would obscure that distinction.

The durable unit is a capability ID, with purpose and responsibilities recorded separately from current paths. A rename changes a locator. A rewrite changes implementation. A split names successor responsibilities. Each can preserve the history that explains why the behavior exists, which signals show it failing, and what peers depend on it.

The operating procedure lives once, in [the continuous-synthesis skill](../skills/continuous-synthesis/SKILL.md). It connects observation, a bounded proposal, a peer response, composition evidence, and a retained lesson. This page explains its place in Synbios rather than duplicating the procedure.

## Source, practice, and execution

The skill is cross-harness text that a Codex, Muse, Exo, or other agent can read. The optional [local coordinator reference](../skills/continuous-synthesis/references/local-coordinator.md) connects that text to the experimental coordination and stewardship CLI. The coordinator records intentions, isolated alternatives, and observations; stewardship records preserve capability responsibilities and adaptation history. Neither substitutes for an agent doing the work or for tests of the composed behavior.

Keep adoption claims separate:

- **Source available:** the skill and prototype are present in a checkout.
- **Instruction installed:** a verified harness entry point points to the skill.
- **Session adoption observed:** a fresh session actually reads and applies it.
- **Runtime behavior observed:** an execution on the intended target demonstrates the claimed behavior.

Changing a startup file does not establish that an existing session reread it. Registering an actor does not connect, authenticate, or launch a harness. This practice creates no daemon, automatic rollout, or expanded authority.

## Discoverable operating entry point

A repository or harness maintainer can adapt this short snippet to its verified instruction mechanism. Resolve the link relative to that mechanism or use a stable repository URL; do not assume every harness discovers the same directory.

> For substantial capability, interface, or dependency changes, read `skills/continuous-synthesis/SKILL.md` in the Synbios checkout. Preserve the human purpose and stable capability identity across redesigns; adapt with affected peers and retain composition evidence and lessons. Use existing task authority and project records. Report instruction installation, observed session use, and live runtime behavior separately.

Keep the substantive procedure in the skill and link to it from operating instructions. Installation is a separate action; these source files do not enroll future sessions by themselves.

## A small reciprocal pilot

Use two independently running agents for a durable handoff capability. One stewards the producer; the other stewards the consumer. The purpose is that a successor can continue authorized work from a retained handoff after implementation paths change.

The producer observes that a handoff contains an obsolete path after a rename. It proposes a stable capability ID with separately maintained implementation links. The consumer reconstructs the task from that proposal and responds with any missing responsibility or evidence. They revise the contract within the task scope and test the combined flow against both the original and renamed layout, plus a missing-reference case. The consumer should surface missing evidence instead of inventing continuation state.

Retain the purpose, both peer responses, tested revisions, evidence limits, and next action in one capability record. A fresh session should be able to identify the responsibility and continue from the record without either author's conversational memory. If one process merely labels its own entries as two peers, describe it as a protocol demonstration; independent participation needs actual separate agents.
