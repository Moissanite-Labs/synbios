# RFC: proof evidence for agentic development

**Status: exploratory proposal.** No verifier, programming language, merge policy, or dependency has been adopted. This document is a starting point for Synbios contributors, not an implementation or a promise that every agentic task can be proven correct.

## Motivation and recommendation

The founder asked whether Synbios could build on [Bend](https://github.com/bendlang) so agentic work is formally verifiable and output quality improves. The opportunity is substantial: a machine-checked proof can establish that a precisely modeled implementation satisfies a stated property. The useful question is which properties and boundaries are worth proving, and whether the resulting evidence improves real outcomes enough to justify its cost.

Treat formal verification as a prospective Synbios capability with a **pluggable proof-evidence interface**. Evaluate Bend 2 as a first candidate, without requiring all Synbios or user projects to use Bend, or making Bend the foundation of the whole forge. Other engines and non-proof tests may later supply complementary evidence. No real merge or policy enforcement is authorized by this RFC.

## What Bend offers and what it does not

The current upstream project calls Bend 2 a new language; its documentation says Bend 1 programs and HVM do not carry over. Its [changelog](https://github.com/bendlang/bend/blob/main/CHANGELOG.md) dates version 2.0.0 to September 17, 2026. The [guide](https://github.com/bendlang/bend/blob/main/guide/GUIDE.md) describes dependent types and a convention in which people write `LAWS.bend` and agents provide code and proofs in `PROOF.bend`. Its `--verdict` mode rechecks translated terms using a BendTT kernel with a proof in Lean; the translation can be written to a `.bendtt` file for inspection.

Upstream also describes a young toolchain, no tactics or proof search, and limited libraries, including no built-in TLS, HTTP, or JSON at the time of the cited README. It says the ordinary checker is not proven, the parser and translation into the kernel are not proven, and compiled backends can differ from the modeled semantics. Foreign code and `@unsafe` are outside the guarantee described for `--verdict`. Recheck these [upstream limitations](https://github.com/bendlang/bend/blob/main/README.md#limitations) against the exact version selected for any future experiment; the links track a changing upstream.

A valid proof establishes a relationship between a formal model and a specification, subject to its assumptions and trusted computing base. It does not establish that the specification expresses the human's actual intent, that a user experience is good, that external inputs are true, that a product has business value, or that real-world actions are authorized or safe. Tests, review, authorization, and operational controls still matter.

## Proposed evidence workflow

1. A person independently reviews the property and assumptions before an agent implements it. Preserve the reviewed laws and their revision identity; do not let the agent silently rewrite its own target.
2. An agent proposes implementation, proof, and tests. A separate verifier adapter produces a structured evidence record; Synbios consumers can inspect it without assuming every adapter has the same guarantees.
3. Bind evidence to hashes of the exact source, reviewed specification/laws, proof, translated artifact, verifier and toolchain versions, and relevant configuration and dependencies. Include the result and its scope, assumptions, time, and a reference to the law review. Hashes identify content; they do not themselves prove authenticity or trustworthy execution.
4. Re-run or mark evidence stale whenever any bound input, specification, verifier, toolchain, or relevant configuration changes. An old proof must not be displayed as evidence for a new revision. Define how evidence is authenticated, stored, independently reproduced, and revoked before treating it as a trustworthy platform signal.
5. Treat changes to laws as substantive review changes. A law change invalidates earlier evidence, requires an independent comparison against the previous intended property, and must not be accepted merely because a weaker law proves more easily. Track the reviewed law version and proof together.

An adapter should distinguish at least **verified**, **failed**, **stale**, and **unavailable** outcomes, identify the exact property and tool version, and never convert an uncheckable or unsupported case into success. The exact wire format, attestation and identity mechanism are open. A future implementation needs explicit trust boundaries between the law author, agent, verifier runner, evidence store, reviewer, and any policy consumer.

## Pilot: a pure merge-eligibility predicate

Start in **shadow mode**: evaluate a pure model and report evidence, without granting merge authority, changing live rules, or blocking a real repository. The pilot asks whether a candidate change has an approval from someone other than its author for the exact candidate revision.

Let `A` be the claimed author ID, `C` the candidate commit ID, and `R` a supplied set of review records. Each record has a claimed reviewer ID, a reviewed commit ID, and a review state. Define the candidate predicate as follows:

```text
eligible(A, C, R) iff there exists r in R such that
  r.state == APPROVED
  and r.reviewer_id != A
  and r.commit_id == C
```

The proposed core law is: **if the predicate returns eligible, such a non-author approval for the exact candidate revision exists in the supplied records.** Independently review the complete law and input assumptions before attempting proof. The model treats the supplied IDs, approval state, and commit IDs as data; it does not authenticate them or establish that an approval remains valid in a live service.

The test set must include an approving non-author on the exact revision that is **allowed**, as well as no approvals, author-only approval, non-approval states, and stale-commit approval that are **denied**. Include a mixed case containing both an irrelevant stale review and a valid current review. Positive cases prevent an implementation that simply rejects everything from passing the examples. Mutate the modeled predicate by removing each of the approval-state, non-author, and exact-commit conditions; each mutation must be caught by the law, tests, or both. If a mutant survives, strengthen the independently reviewed property or cases before claiming the pilot is meaningful.

Pin and retain a reviewable evidence bundle containing the source, `LAWS.bend`, `PROOF.bend`, translated `.bendtt`, toolchain and dependency identities, verifier configuration, result, and content hashes. Review the translation against the intended law because the source-to-kernel translation is not itself proven. Record the observed behavior of unsafe or foreign dependencies; exclude them from the claimed proof scope unless separately justified.

Authentication and identity binding, review dismissal and freshness, accurate repository inputs, atomic enforcement at the Git host, concurrent changes and time-of-check/time-of-use races, external policy bypass, and compiled/runtime behavior are **outside this pure proof**. A future real gate must address these separately, with its own design and tests.

## Work breakdown and acceptance criteria

1. **Model and review.** Write the input types, predicate and laws, enumerate assumptions, and have a reviewer independent of the agent validate the intended property and positive cases. Acceptance: a human can explain what the proof will and will not establish.
2. **Candidate experiment.** Select and pin a Bend 2 version after review; implement the pure predicate and proof in an isolated experimental workspace. Acceptance: the selected toolchain checks the reviewed law and the `--verdict` result is recorded together with the translated artifact. No version or dependency is selected by this RFC.
3. **Evidence and mutation checks.** Create a reproducible evidence bundle and run the positive, negative, and three mutation cases. Acceptance: the non-vacuous positive example passes, negatives fail as specified, each mutant is detected, and changes to bound inputs cause stale evidence rather than reuse.
4. **Shadow integration design.** Specify how a candidate adapter would publish and display results without changing any live merge behavior. Acceptance: evidence clearly identifies source, law, proof, toolchain, assumptions, result, and failure/staleness; unsupported verification remains distinguishable from success.
5. **Evaluation.** Record defects or mismatches found, proof and specification effort, verifier latency, failure and reproducibility rates, and independent law-review burden. Compare with a conventional implementation plus tests on the same cases.

Continue to a broader pilot only if reviewers find the properties meaningful, independent review and artifact binding workable, the experiment reproducible, and the measured benefits worth the cost. Stop or redesign if the model is vacuous, laws cannot be reviewed reliably, the trust boundary is unclear, tooling or latency prevents reproducibility, or verification provides little benefit over tests. Any transition to a live gate requires a separate design and authorization.

## Open decisions

Which properties and projects justify proofs? Who can author, approve, or change laws? What input semantics cover dismissed or superseded reviews? How are identity, artifacts, toolchains, evidence and attestations verified? Which engines and versions are supported, and what is their trusted computing base? How do adapters expose partial coverage, failures, unsafe or foreign assumptions, and staleness? What performance and reviewer-cost thresholds warrant continuation? How could a future real gate avoid race conditions and policy bypass? None is resolved here.
