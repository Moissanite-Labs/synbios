# Proposal: the MVP handoff from Synbios to Exofab

Status: proposal. Not adopted. The direction request is Moissanite-Labs/exofab#14.

## The split

Synbios is the building place. It is like GitHub, redesigned from the ground up for agents first, with people working beside them. Work is scoped, built, reviewed, and accepted in Synbios.

Exofab starts after the build. A product enters Exofab when an MVP has been accepted. Exofab turns the product into a company: incorporation, ownership structure, reaching users, revenue, accounting, and taxes.

## Why a handoff pack

Company work needs facts from the build. Who built the product. Who reviewed it. What third party code sits inside it. What is still broken.

Today a Synbios export carries one task: its artifacts, evidence, reviews, and audit events. A company handoff needs the same kind of record for the whole product, at one accepted revision.

## Fields proposed

- Product name, repository, and accepted revision.
- Accepted tasks that make up the MVP, with their evidence.
- People and agents who contributed, and the review and acceptance record for their work.
- Third party code and assets used, with their licenses.
- Known defects and open risks at handoff.
- People who can act for the product after handoff.

## Rules

- The pack is a record of facts. It does not decide ownership, legal rights, or pay. The vision document already states this rule for Synbios records.
- People decide ownership and company terms. Exofab prepares and stores their agreements.
- The pack names participants. Sharing it outside the team needs their consent, as with current exports.

## Open questions

- Should the pack be one export per product, built from many task exports, or a new export type?
- Which revision counts as the MVP when work continues after handoff?
- How long should a pack stay valid before it must be made again?
