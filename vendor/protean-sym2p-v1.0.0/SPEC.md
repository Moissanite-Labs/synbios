# SYM-2P/1.0 - specification

Normative specification for SYM-2P: a compact, versioned message language carried
as one canonical JSON object per line inside durable text artifacts. This file is
the norm. Evidence and provenance live in `AUDIT/`; nothing in `AUDIT/` is
normative.

Role ids in this specification and its examples are neutral placeholders: `relay`
(the human-facing boundary and project router), `cos` (the in-project
coordinator), and the specialist roles (`research`, `arch`, `design`, `builder`,
`qa`).

## 1. Locked

Anything in this section is normative. A change to a locked item requires a
profile or major version increment, a decoder migration, partner-swap and replay
tests, and continued access to prior audit logs. Extensions stay namespaced under
`ext` until promoted.

| # | Locked decision |
|---|---|
| L-1 | **Wire envelope `v` is fixed at integer `2`.** The string "SYM-2P/1.0" is the profile name, not the wire field. |
| L-2 | Profile revision travels in `ext.sym2p.rev` (default `"1.0"` when absent). `ext.sym2p` is explicitly optional: a receiver that ignores it still holds a complete, safe packet. This is the only sanctioned use of `ext` in 1.0; everything else under `ext` is experimental and ignorable under the same condition. |
| L-3 | **Carrier = one canonical JSON object per line**, UTF-8, no insignificant whitespace, inside text artifacts (briefs, receipts, ledger rows). A packet line parses as JSON on its own; surrounding prose is English. No prefix may precede the `{` on a packet line, because a prefix breaks the "valid UTF-8 JSON object" check. |
| L-4 | **Canonical key order is fixed and exact**, with no reordering, no added keys, and no nulls: `v,id,tk,prj,f,t,a,s,st,cf,err,cov,ev,ce,cond,ops,rq,base,exp,auth,ext`. Optional fields are omitted when absent, never emitted as `null`. |
| L-5 | **IDs and refs use this grammar verbatim.** `ID := [a-z][a-z0-9_-]{0,31}`; `REF := ID [":v" VERSION]`; `VERSION := [1-9][0-9]*`. No aliases, no prose inside IDs, no dotted or extended ids. Version is a separate facet and is never encoded inside the identifier. |
| L-6 | **One act, one packet.** Exactly one act from the fixed 12-value enum per packet. Multi-act messages split, or declare one explicit transaction. Multi-recipient packets are not legal in 1.0: `t` is a single id ref, and a group send is N packets plus one routing-state row naming the set. |
| L-7 | **Recipient addressing is single and explicit.** Sender `f` and recipient `t` are stable agent or role ids. No inferred recipients, and no subject inferred from earlier turns. |
| L-8 | **`cf`, `cov`, `err` are integers 0-99 and are routing signals only**, never presented as a calibrated probability. Confidence is calibrated per role and task family, never fleet-wide. |
| L-9 | **Cross-profile confidence comparison is suspended.** An absolute `cf` delta must not trigger a dispute across heterogeneous providers or models. Until per-role calibration data exists, disputes open on evidence conflict or on explicit disagreement, not on raw score deltas. |
| L-10 | **Bases are explicit.** Every mutation carries `base`, an object ref with a version. Apply is atomic or it does not happen. A mismatch returns `ERR:VER` with the receiver's current version and `rq:"full"`. Silent merge is never permitted. |
| L-11 | **Retries are idempotent.** A retry keeps the original `id` and payload hash; a duplicate returns the prior terminal response without re-running work. The dedup key is the pair `(f,id)`. |
| L-12 | **Out-of-order packets queue only when the missing predecessor is known and bounded**; otherwise the receiver requests full state. |
| L-13 | **Conflicts become disputes or a coordinator replan.** Last-write-wins is forbidden for plans, decisions, and approvals. |
| L-14 | **Published objects are immutable.** A revision is a new version with a `sup` (supersedes) pointer; a published version is never edited in place. Old versions stay available for replay and audit until retention permits deletion. |
| L-15 | **Every object carries canonical sha256 integrity and lineage.** The hash is computed over the canonical form; `deps` and `sup` record derivation. |
| L-16 | **Fail closed.** Unknown codes, stale state, unresolved references, and invalid or expired authorization never trigger guessed behavior. |
| L-17 | **English is required at exactly three places and is permitted as the recovery ladder elsewhere:** the user boundary (relay, inbound and outbound); dispute opening and resolution records; and the authorization approval record, which holds the exact user-approved action and scope verbatim. A fallback never weakens authorization or protected semantics. |
| L-18 | **No latent channel.** Text JSON over durable file artifacts is the only inter-agent surface. No hidden-state, embedding, or key-value cache exchange; no cross-profile in-memory state; no assumption that anything survives unless it is written to the delegation tree. Prompt-prefix reuse is an optimization, never a channel. |
| L-19 | **Coordinator authority is scoped, not supreme.** The coordinator owns routing, the ledger, synthesis, escalation, and the stop rule. It does not own stage authorities. Architecture invariants, QA verdicts, research and writing, design, and implementation outrank the coordinator inside their own domain; a coordinator that disagrees opens a dispute or escalates to the relay. |
| L-20 | **Stop rule is explicit and recorded.** Collaboration ends when acceptance criteria are met, when the marginal value of another call is below its cost, when a hard budget is reached, or when policy requires human resolution. Invoking the rule is a ledger row, not a silent stop. |
| L-21 | **Retention classes are attached to every object:** `ephemeral` (delete at task close), `task` (keep through the audit window), `project` (keep across related tasks), `regulated` (policy-defined, required for approvals and irreversible actions). |
| L-22 | **`exp` is an integer step index, not a wall-clock time.** Wall-clock timestamps appear only inside the `auth` object and in ledger rows. |

## 2. Roles and state

| Role | Authority | Must never |
|---|---|---|
| Relay (English boundary, project router, issuer of authorization refs) | Classifies inbound requests, maps a project to its coordinator, attaches explicit user approval, and renders state in English without exposing packets | Invent scope, or widen a prior approval |
| Coordinator (task owner, policy enforcement point) | Decomposes, sets acceptance criteria, chooses specialists and edges, holds authoritative routing state, opens disputes, synthesizes verified results, applies the stop rule | Override a stage verdict (L-19) |
| Specialist | Reads only assigned objects and dependencies, returns claims, evidence, counter-evidence, and uncertainty, publishes durable output, and sends a reference | Restate history, contact peers without an opened edge, or claim completion against unmet criteria |
| Blackboard (durable shared state) | Stores once, versions every mutation, retains provenance, enforces access and retention | Any silent merge (L-10) |
| Packet | Carries the minimum sufficient state change | Carry full object bodies except for `rq:"full"` recovery |
| Routing state | Records gate outcome, edge grants, and budgets, so sparse routing stays observable | Lose the reason a message was silent |

Topology: a star centered on the coordinator. Specialists publish to the
blackboard and notify the coordinator. A specialist-to-specialist edge is
temporary, scoped to one task, opened only when the receiving specialist owns the
affected state, and recorded as an edge grant in the routing state. All-to-all
specialist conversation stays out of version 1.

## 3. Packet header - exact field set and fixed order

```
{"v":2,"id":"<id>","tk":"<id>","prj":"<id>","f":"<id>","t":"<id>","a":"<act>",
 "s":"<ref>","st":"<status>","cf":<int 0-99>,"err":<int 0-99>,"cov":<int 0-99>,
 "ev":["<ref>"],"ce":["<ref>"],"cond":["<str>"],"ops":[<op>],
 "rq":"<req>","base":"<ref>","exp":<int>,"auth":{...},"ext":{...}}
```

| Field | Order | Required | Type / domain | Meaning |
|---|---|---|---|---|
| `v` | 1 | yes | integer, exactly `2` | protocol major version |
| `id` | 2 | yes | ID | sender-unique message id, stable across retries |
| `tk` | 3 | yes | ID | task identifier |
| `prj` | 4 | yes | ID | project routing identifier |
| `f` | 5 | yes | ID | stable sender |
| `t` | 6 | yes | ID | stable recipient (single) |
| `a` | 7 | yes | act enum | exactly one speech act |
| `s` | 8 | conditional | REF | subject object ref, resolvable or created by an allowed act |
| `st` | 9 | no | status enum | epistemic status when relevant |
| `cf` | 10 | no | integer 0-99 | sender confidence, a routing signal |
| `err` | 11 | no | integer 0-99 | self-estimated material-error chance |
| `cov` | 12 | no | integer 0-99 | evidence-space coverage |
| `ev` | 13 | no | array of REF, unique | supporting evidence |
| `ce` | 14 | no | array of REF, unique | counter-evidence |
| `cond` | 15 | no | array of strings | conditions and holds |
| `ops` | 16 | conditional | array of typed ops | delta operations for `a:"update"` |
| `rq` | 17 | no | request enum | requested receiver action |
| `base` | 18 | conditional | REF with version | assumed state, required for every mutation |
| `exp` | 19 | no | integer step index | expiry step |
| `auth` | 20 | conditional | object | authorization envelope, required for irreversible or expanding actions |
| `ext` | 21 | no | object | namespaced extensions, ignorable only when the base packet remains complete and safe |

Required for all packets: `v,id,tk,prj,f,t,a`. Every other field is
act-conditional and omitted when absent.

**Wire enums (fixed, no additions or removals):**

- Acts `a` (12): `assign, assert, question, answer, propose, accept, reject,
  challenge, verify, update, escalate, done`.
- Requests `rq` (9): `ack, upd, ver, rev, exec, src, exp, full, decide`.
- Statuses `st` (7): `observed, inferred, assumed, proposed, disputed, rejected,
  verified`.
- Errors (8, carried in `ext.err` for error packets): `ERR:SYN, ERR:SEM, ERR:REF,
  ERR:VER, ERR:EXP, ERR:AUTH, ERR:AMB, ERR:POL`.
- Object type prefixes `type` (13): `t, q, c, h, e, p, act, r, d, k, u, z, f,
  dis`.

**Implemented subset for 1.0.** A validator must accept and reject against the
full enums above, because an unknown enum value is a rejection. The exercised
operational subset is `assign, assert, answer, verify, update, done` plus
`escalate` for acts, `ack, upd, ver, rev, exec, src, full, decide` for requests,
and all seven statuses. The unexercised values remain reserved and legal: they
are not removed, because removal is a semantic change requiring a version
increment.

## 4. Object conventions

Root: a delegation directory for the project, with `briefs/`, `receipts/`,
`objects/`, and `ledger/` as the object surfaces. The relay owns the project
slug; the coordinator owns placement.

**Object file header block** - required at the top of every brief, receipt, and
object file:

| Metadata | Required | Convention |
|---|---|---|
| Identity | yes | `id` + `type` + `tk` + `prj` (type prefix from the type list) |
| Version | yes | monotonic integer `v`, plus a `sup:["<id>"]` supersedes chain |
| Authorship | yes | `by` = creating role id; `at` = ISO-8601 UTC creation time or step |
| Integrity | yes | `hash` = `sha256:<hex>` over canonical content |
| Lineage | yes | `deps:[refs]` (dependency) and `sup:[refs]` (derivation) |
| Governance | yes | `acl:[role-ids]` and `ttl` in {ephemeral, task, project, regulated} |
| Body | yes | `body` - the content, stored once; packets reference it |

Immutability and versioning at file level:

1. `<id>.md` is version 1. A revision is written as `<id>.v<N>.md`, a new file,
   never an in-place edit of a published file (L-14).
2. The revision's header carries `sup:["<id>"]`, or `sup:["<id>.v<N-1>"]` for
   N greater than 1, and an incremented `v`.
3. Hash, lineage, and publication happen together. Only then is a short
   `update` or `assert` packet emitted naming the new ref, for example
   `{"a":"update","s":"e3:v3","rq":"rev","base":"e3:v2"}`.
4. Artifacts that already exist as version 1 are grandfathered as version 1
   objects: their bare filename maps to `:v1`, with no retrofit and no rewrite.
   New writes conform, and revisions of them follow rule 1.
5. `ephemeral` objects are deleted at task close. `regulated` objects require a
   policy-defined retention window; the window values are an open item (O-4).

Object types in use: `e` evidence, `c` claim, `p` plan, `dis` dispute, `d`
decision, `f` artifact, `act` action, `k` constraint. Required core content per
type: evidence = source, scope, date, extract, caveats; claim = statement,
status, evidence, counter-evidence; plan = steps, owners, dependencies, stop
conditions; dispute = positions, class, needed resolution; decision = options,
selected option, authority, rationale refs; artifact = location, hash, producer,
validation status.

Routing-state rows record, for every dispatch: `(f,id)`, `tk`, `prj`, sender,
recipient, the gate outcome (`sent`, or `silent` with a reason such as
`receiver_state_will_not_change`, `duplicate_or_low_novelty`, or
`expected_value < cost`), the assigned budget, any edge grant, and `exp`.
Without the recorded outcome, sparse routing is unobservable.

## 5. Duplicate, stale, and failure handling

The gate order is locked: reject unless schema, authorization, refs, version, and
policy all pass; stay silent if the receiver state will not change; stay silent if
the message is duplicate or of low novelty; stay silent if the expected value is
below the invocation and processing cost; send a reference when the shared object
already carries the content; otherwise send the canonical packet.

Atomic apply, in exact order: authenticate sender, dedupe `(f,id)`, resolve and
hash the base, validate every operation and precondition, apply all operations in
memory, validate the resulting object, publish one new version, then acknowledge.

| Condition | Behavior |
|---|---|
| Base matches | Apply atomically, publish one new version, acknowledge |
| Base mismatch or stale | Return `ERR:VER` with the receiver's current version and `rq:"full"`. The sender supplies a snapshot or recomputes a delta. No silent merge. |
| Retry of a completed request | Keep the original `id` and payload hash, return the prior terminal response, and do not re-run work |
| Out of order | Queue briefly only when the missing predecessor is known and bounded; otherwise request full state |
| Duplicate or low novelty | Suppress via the gate; nothing is sent, and the ledger records the silent reason |
| Conflict | Open a dispute or ask the coordinator to replan. Last-write-wins never applies to plans, decisions, or approvals. |
| Expired message or approval | `ERR:EXP`, never execute |
| Unauthorized or cross-project | `ERR:AUTH`, denied by default; fail closed when the policy service fails |
| Malformed or ambiguous | `ERR:SYN` or `ERR:AMB`. The recipient names what failed and the minimum recovery it needs, and never guesses intended state. |

Error packets follow the standard envelope with the code namespaced:

```
{"v":2,"id":"...","tk":"...","prj":"...","f":"...","t":"...","a":"answer",
 "s":"<ref>","rq":"full","base":"<ref>","ext":{"err":"ERR:VER","have":"<ref>"}}
```

The code lives under `ext.err`; the sender's `err` score stays a separate integer
field.

**Fallback ladder**, each downgrade logged with the original packet, the failure
code, the recovered interpretation, and the outcome: canonical SYM-2P, then
verbose JSON with the same schema, then concise English with explicit meaning,
then coordinator or human adjudication. A fallback never weakens authorization or
protected semantics.

## 6. Protected semantics (P0-P9)

An encoder may shorten or reference these. It must never remove them when they can
change an outcome.

| Class | Protected content | Carried by |
|---|---|---|
| P0-P2 | Safety constraints, critical evidence, counter-evidence | `cond`, `ev`, `ce`, object types `k`, `e`, `z` |
| P3-P5 | Dissent, scope, provenance | `dis` objects with all positions preserved, `st:"disputed"`, `deps`/`sup`, `s` scope refs |
| P6-P9 | Tool uncertainty, irreversibility, approval, version and integrity | `err`, `cov`, `cf`, `auth`, `base`, `hash`, `exp` |

Rules that follow:

1. **Dissent survives synthesis.** Competing positions are recorded separately,
   and resolution appends a decision without deleting the losing view. Dispute
   objects carry positions, a class (`fact, source, scope, evaluation, causal,
   value, plan, risk`), and the needed resolution.
2. **Resolution contract.** A resolution names the selected position or
   synthesized conclusion, the evidence that changed the result, the adjudicator,
   the remaining uncertainty, and the action impact, and it preserves all prior
   positions.
3. **Canonical test.** After decoding a packet, a compatible receiver must recover
   the same conclusion, evidence set, conditions, uncertainty, dissent, and
   requested action.
4. **Claims are not evidence.** Consequential assertions link to supporting and
   opposing evidence, with provenance retained in the objects. Integrity is
   necessary but not sufficient: a valid packet may still contain a wrong claim.
5. **Protected semantics outrank compression.** An encoding that drops a P-class
   field to save tokens is a defect, not an optimization.

## 7. English boundary, disputes, and authorizations

**Inbound (relay, user to team):** identify the project and its coordinator,
classify the request (new task, update, decision, correction, cancellation,
question), extract scope, constraints, deliverable, deadline, budget, and
acceptance criteria, preserve ambiguity as an explicit unknown rather than
silently filling it, and emit one or more scoped packets.

**Outbound (relay, team to user):** read authoritative objects and the
coordinator's decision, state the result first in plain English, surface material
uncertainty, options, dissent, blockers, and required decisions, never expose
internal packets or chain-of-thought, and keep traceability through internal
references.

**Disputes.** English is permitted and expected for the human-readable resolution
narrative. The typed dispute object remains authoritative, and all positions
persist.

**Authorizations (locked shape):**

```
{"v":2,"id":"<id>","tk":"<id>","prj":"<id>","f":"relay","t":"<coordinator id>",
 "a":"accept","s":"<action ref>","rq":"exec",
 "auth":{"kind":"human_approval","scope":"<object ref with version>",
         "approved_at":"<ISO-8601Z>","expires_at":"<ISO-8601Z>",
         "ref":"approval:<id>"}}
```

The approval record stores the exact user-approved action and scope in English.
The packet carries a reference, never the private conversation text. The executor
verifies that subject, version, scope, and expiry all match. Approval is required
for external sends, publications, purchases, bookings, account changes,
deletions, and other irreversible or consequential operations; for any step that
expands audience, destination, data scope, access, cost, or recurrence; and for
any policy-defined high-risk operation even when a specialist or the coordinator
recommends it. There is no authority by implication: prior approval never
authorizes a broader action, a different destination, a later recurring job, or a
changed object version. Verification of feasibility is not authorization to act.

The home of the authorization verifier and of the approval store is an open item
(O-2). The requirement itself is locked: 100% of irreversible actions carry
matching, unexpired authorization, and consequential decisions are
reconstructable from durable state.

## 8. No-latent-channel rule

1. The only inter-agent surface is UTF-8 JSON text carried in durable file
   artifacts in the delegation tree (L-3).
2. Raw hidden-state, embedding, and key-value cache exchange are out of version 1.
   No supported hidden-state or cache channel is assumed.
3. Cross-profile execution is profile-native, so nothing may be assumed shared
   beyond what is written to disk: no shared memory, no shared process state, no
   cross-profile in-language context. If it is not in an object, it does not
   exist.
4. Prompt-prefix reuse across calls is a platform-conditional optimization, not a
   channel. Byte-identical prefixes do not guarantee shared caching or identical
   generation across heterogeneous providers, so no correctness, latency, or cost
   claim may depend on it.
5. Canonical key order buys comparability, signing, and logging stability. It is a
   validation discipline, not a generation guarantee fleet-wide.
6. Anything a receiver needs and did not receive must be requested explicitly
   (`rq:"src"`, `"full"`, or `"exp"`), never inferred.

## 9. Migration boundary

| Phase | Status at specification time | In SYM-2P/1.0 |
|---|---|---|
| 1 - Instrument and constrain: ids, accounting, purpose labels, authorization events, state-change-only rule, with English coordination as the baseline | Already the operative mode: briefs, receipts, ledger and inflight rows, and profile-native dispatch serve as the English baseline | Locked where it intersects sections 3 to 5: ids, `(f,id)` dedupe, purpose as the single act, authorization events, and the state-change-only rule |
| 2 - Deploy the blackboard and the protocol: schema validation, object storage, versioning, references, deltas, idempotency, error packets, and the fallback ladder | Not yet deployed. This specification is the Phase 2 specification. | Yes: this is the implemented scope. Section 3 to section 5 are implemented; section 4 is the storage convention |
| 3 - Optimize routing: novelty detection, expected-value gating, dynamic specialist selection, temporary direct edges, prompt-prefix reuse, thresholds tuned by task family | Not started. Gate predicates are named but unspecified. | No: explicitly out of scope, named and not implemented |

Additional boundary rules:

- Composition is defined, not owned, here. This specification states conventions
  that other procedures reference. It edits none of them.
- Platform assumptions in the source are unmet and must not be simulated
  silently. Stable identities, a project and task namespace, persistent storage,
  an authorization hook, platform-scoped access control, a hash service, replay
  protection, and immutable logs have no platform provider assumed here. Version
  1.0 substitutes file conventions for storage and namespace, a sha256 computed
  in process for hashes, and file immutability for logs. Transport signing is not
  implemented (O-1).
- No wire change may ride along with an implementation. Extensions stay under
  `ext` until promoted, and promoted fields arrive with a version increment plus
  decoder migration and partner-swap and replay tests.
- Grandfathering: existing version 1 artifacts are readable as they are and are
  not rewritten by the migration.

## 10. Open items

These are unresolved. Shipping them open is deliberate: publication does not close
them.

| # | Open item | Status / interim rule |
|---|---|---|
| O-1 | **Transport signing.** Cross-profile file handoffs are distributed transport. 1.0 locks canonical sha256 hashes and stable identities but no asymmetric signing. | Interim: hash-only integrity, single-machine trust assumption. Revisit if an external partner joins. |
| O-2 | **Authorization verifier and approval store.** The requirement is locked. The home is not: which role or checker verifies subject, version, scope, and expiry, and where approval records live. | Interim: `auth` objects are `regulated`-class objects in the delegation tree, and verification is a pre-execution gate performed by the executing stage, logged in the routing state. |
| O-3 | **Routing predicate definitions.** The predicates that decide whether a message changes receiver state, whether it is novel, and whether its expected value exceeds its cost are named but undefined. | Interim: only mechanical predicates are enforced in 1.0. Value gating is Phase 3. |
| O-4 | **Retention windows.** Classes are named but no durations exist. `regulated` is policy-defined with no policy attached. | Interim: `ephemeral` is deleted at task close, `task` and `project` are not deleted without a coordinator decision, and `regulated` is never deleted. |
| O-5 | **Per-role calibration.** `cf`, `cov`, and `err` are heuristic until calibration for a role and task family exists. Cross-profile comparison is suspended (L-9). | Interim: evidence-anchored dispute triggers only, on evidence conflict or explicit challenge. |
| O-6 | **Dispute and decision home, and closing authority.** Which surface holds dispute and decision objects, and who may close a dispute: the coordinator alone, or the stage owner whose domain is disputed. | Interim per L-19: the stage owner may close a dispute inside their domain. The coordinator may close it otherwise, and must record the adjudicator and the remaining uncertainty. |
| O-7 | **Minor-version convention.** Whether a profile minoring scheme is needed now, beyond `ext.sym2p.rev`. | Interim: L-1 and L-2 apply, `v` stays `2`, profile revisions that add no required field are legal, and a receiver may accept them only while all unknown extensions are optional. |
| O-8 | **Fallback logging surface.** Who logs each downgrade, and where the metric lives. | Interim: the fallback event is a routing-state row, and a QA verdict must report fallback and parse rates. |
| O-9 | **Group addressing.** The field rules allow one recipient or a declared group, while the schema fixes `t` to one id ref. | Locked for 1.0 as single-recipient (L-6): a group send is N packets plus one routing-state row naming the set. Reopens only with a version increment. |

## 11. Acceptance criteria

**For an implementation of this specification:**

| # | Criterion |
|---|---|
| M-1 | The packet validator enforces the exact fixed key order, the required seven fields, the full enums, integer 0-99 scores, and the ID and REF grammar. It rejects duplicate keys, unknown required enums, floats where integers are required, and out-of-grammar ids. |
| M-2 | The canonicalizer emits compact UTF-8 JSON with no insignificant whitespace and omits absent optionals, never `null`. |
| M-3 | Dedupe on `(f,id)` returns the prior terminal response on a duplicate and never re-runs work. Retries preserve the original `id` and payload hash. |
| M-4 | A stale or mismatched base returns `ERR:VER` with the receiver's current version and `rq:"full"`. No silent merge path exists in the code. |
| M-5 | Object writes are append-only versions, `<id>.v<N>.md` with `sup` and an incremented `v`. The tooling refuses to rewrite a published file. |
| M-6 | Every object carries id, type, task, project, version, authorship, sha256 hash, dependency and supersession lineage, access list, and retention class. |
| M-7 | The profile revision tag is emitted with its default, and unknown `ext` keys are ignored rather than rejected when the base packet is complete and safe. |
| M-8 | All eight error codes are typed, and every failure path emits a typed outcome instead of a guess. |
| M-9 | Every dispatch writes a routing-state row with the gate outcome and the silent reason, the budget, any edge grant, and the expiry. Stop-rule invocations are recorded. |
| M-10 | The thirteen fault-injection cases each produce a safe typed outcome, as executable fixtures. |
| M-11 | No latent channel is introduced: no cross-profile in-memory state, no key-value or hidden-state exchange, and no correctness or cost dependency on provider prompt caching. |
| M-12 | Nothing outside this specification's surface is implemented. Phase 3 features stay unimplemented. |

**For an independent verification of that implementation:**

| # | Criterion |
|---|---|
| S-1 | Semantic: 99% or more schema-valid packets on held-out traces, and zero silent interpretation of malformed input. |
| S-2 | Behavioral: no material task-quality regression against the English multi-agent baseline. |
| S-3 | Economic: measurable cost or latency reduction after counting retries, storage, and coordinator overhead. Shorter messages are not success if the system makes more calls or falls back more. |
| S-4 | Governance: 100% of irreversible actions carry matching, unexpired authorization, and consequential decisions are reconstructable from durable state. |
| S-5 | Resilience: stale, duplicate, reordered, unauthorized, and cross-project packets cause safe typed outcomes. |
| S-6 | Canonical test: decoding a packet recovers the same conclusion, evidence set, conditions, uncertainty, dissent, and requested action. |
| S-7 | Dissent and provenance: disputes are preserved through synthesis, claims carry provenance and counter-evidence, and no losing position is deleted. |
| S-8 | Fault injection: all thirteen cases are exercised with recorded results. |
| S-9 | Protected semantics: a finding that any P0-P9 field was dropped for compression is a blocking defect. |
| S-10 | Verdict form: the verdict is a PROCEED, HOLD, or BLOCK line backed by evidence refs and a routing-state row, and dissent on the verdict is recorded rather than suppressed. |

**What this specification does not cover.** The operational surfaces the protocol
runs on are outside the specification's scope and remain bound to the open items
above.
