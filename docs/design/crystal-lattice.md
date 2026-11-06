# Crystal Lattice: fixed design, real mission data

The selected design is **Direction 4 — Crystal Lattice merged**, not the simplified public-intake screen. It is the fixed user-facing touch point for the Synbios rebuild requested in [issue #58's feedback](https://github.com/Moissanite-Labs/synbios/issues/58#issuecomment-6689944669).

## Source of truth

| Source | Pinned revision | Role |
| --- | --- | --- |
| [Exofab PR #17](https://github.com/Moissanite-Labs/exofab/pull/17) | [`ee02b4bba59c5f978e90039d01564b770fbe8ae4`](https://github.com/Moissanite-Labs/exofab/tree/ee02b4bba59c5f978e90039d01564b770fbe8ae4/docs/design/ui-directions) | Designer's chosen merged composition, specification and screenshots |
| [Exofab PR #20](https://github.com/Moissanite-Labs/exofab/pull/20) | [`8adbd749693f227fcbe65d5a660d5fae1d428edc`](https://github.com/Moissanite-Labs/exofab/blob/8adbd749693f227fcbe65d5a660d5fae1d428edc/site/index.html) | Interactive implementation, local font fallbacks, keyboard/reduced-motion behavior |

These sources contain fictional Tidepool data. Their examples and the handwritten fictional name are not user identities, real approvals or Synbios telemetry. No licensing or economic rights are inferred from this adaptation.

## Preserve the composition

- The crystal sits beside the decision panel and its source margin. Below are Crew, Live work and Trace.
- The census has five rings: **Idea / Shape / Prototype / Build / Ship**.
- The axial hex grid uses `S = 31`, `x = S × √3 × (q + r/2)`, `y = S × 1.5 × r`, with SVG `viewBox="-204 -184 408 368"`.
- Carbon circles represent people and silicon diamonds represent agents. Pending, forming, bonded and ghost styles keep the original vocabulary.
- Dependency/provenance threads, source highlighting and the signature area remain part of the decision experience.
- Retain the original dark surfaces, carbon/silicon palette, typography hierarchy, census styling and responsive composition. The interface uses local fallbacks rather than fetching fonts.
- Preserve keyboard access, visible focus, mobile source access and reduced-motion behavior.

The shape is fixed; the fictional population is not. Real tasks can be fewer or more than the visible ring positions. Counts and navigation must expose all work; overflow must never make tasks disappear silently. Ghost positions are visual context, not invented tasks.

## Bind the design to meaning

| Visual element | Runtime meaning |
| --- | --- |
| Project heading | Mission name and intended outcome |
| Ring | Explicit work stage; separate from execution/review status |
| Core / real nodes | The recorded mission goal at the core, and work slices with title, owner, criteria and scope |
| Pending state | An actual open decision or review request |
| Forming state | Recorded unfinished work; not proof of a running process |
| Bonded state | Work accepted through the artifact/evidence/review rules |
| Sources and threads | Actual task dependencies and recorded evidence |
| Crew | Identities and their allocations; no inferred session heartbeat |
| Progress | Latest participant report, labeled and timestamped |
| Signature area | Recorded human choice and its identity; no claim of cryptographic or legal signature |
| Trace | Persisted events that explain changes to the mission |

Unknown metrics stay unavailable. Tree differences do not imply a human decision. Clicking approval changes the relevant local record only after the server accepts it; animation cannot manufacture success or trigger unrelated external actions.

## Product acceptance

The screen must answer, without a separate technical explanation: **What are we trying to achieve? What is being worked on? Who owns it? What is blocked? What needs me next?**

A user can create or request slices, assign them, copy a complete agent brief, inspect returned work and respond to decisions from this interface. Identifiers, hashes and protocol detail belong in inspection views. Browser tests must use the real local backend for mutations and check persistence, stale-state errors, keyboard use and narrow layouts. Visual review compares the actual implementation with the pinned reference; API tests alone cannot establish design fidelity.

This rebuild preserves the existing acceptance and audit core. Autonomous model execution, filesystem enforcement and cross-store migration are separate capabilities with their own evidence requirements.
