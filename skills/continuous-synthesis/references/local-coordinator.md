# Optional local coordinator

Use this reference only when the task uses the Synbios local collaboration prototype. The practice in the parent skill does not depend on this implementation.

From a Synbios checkout, the coordinator is `experiments/local-collaboration/prototype/coordinator.py`; the capability ledger is `experiments/local-collaboration/prototype/stewardship.py`. Consult each command's `--help` for its installed interface and [the prototype documentation](../../../experiments/local-collaboration/prototype/README.md) for coordination semantics. A copied skill needs the Synbios checkout to execute those commands.

The existing coordinator uses a separate SQLite database outside the target workspace. All cooperating sessions for that workspace must use the same database. Register caller-asserted actors, declare read/write scopes, inspect conflicts and current observations, and use isolated alternatives for competing implementations when useful. Declarations report conflicts; they do not lock source files or enforce cooperation. An alternative's recorded acceptance does not integrate its bytes.

The stewardship ledger adds durable capability responsibilities and adaptation history. Keep capability identity distinct from an actor label, file path, intention, or isolated alternative. Record the actual actor making each proposal or response; ledger labels are assertions rather than authentication. Evidence references should identify the actual tested candidate and combined path, with limits. A recorded successful outcome must not stand in for a test or observed integration.

## Stewardship commands

Run from `experiments/local-collaboration`. Each mutating command reads one JSON request file; keep local request files outside tracked source. Use the same external `STATE_DB` as the coordinator.

```sh
python3 prototype/stewardship.py --db "$STATE_DB" charter charter.json
python3 prototype/stewardship.py --db "$STATE_DB" propose proposal.json
python3 prototype/stewardship.py --db "$STATE_DB" check PROPOSAL_ID
python3 prototype/stewardship.py --db "$STATE_DB" respond response.json
python3 prototype/stewardship.py --db "$STATE_DB" evidence evidence.json
python3 prototype/stewardship.py --db "$STATE_DB" close closure.json
python3 prototype/stewardship.py --db "$STATE_DB" resume --capability CAPABILITY_ID
```

A charter records `capability_id`, `actor`, `purpose`, `success_signals`, `failure_signals`, `scope`, and `peers`. Scope and implementation locators can change without abandoning the ID. Preserve purpose changes explicitly rather than using a successful test to redefine the original responsibility.

Include every peer listed by each affected charter in the affected capability set. Required responders are the distinct steward actors of those charters, excluding the proposer; at least two distinct actor labels must participate.

A proposal names `actor`, affected `capabilities`, `intention_id`, `alternative_id`, and `rationale`. This local pilot uses at least two capability IDs for a reciprocal adaptation. The intention and alternative connect responsibility to a declared change and a real candidate directory. Include all affected capabilities; listing a dependency as a peer alone does not establish that its steward participated.

A response names `actor`, `proposal_id`, `proposal_digest`, `candidate_digest`, `decision` (`support`, `revise`, or `decline`), and `comment`. Copy the exact current digests from the proposal check instead of guessing them. A response to older bytes does not cover a later candidate.

An evidence request names `actor`, `proposal_id`, both digests, `kind` (`test`, `analysis`, or `behavior`), `outcome` (`passed`, `failed`, or `unavailable`), and `summary`. A stored assertion is not independently executed evidence: include the actual command, tested revision or tree, result, and limits in the summary or a durable referenced artifact.

A closure names `actor`, `proposal_id`, and `lesson`. Closure retains the final observation, including stale or unsupported proposals; it does not require readiness. Its `advisory_ready` or `not_ready` label describes the closure observation. `check` reports `ready` only while the proposal is current, all required peers support it, each latest evidence assertion per actor and kind reports passed and at least one latest test or behavior assertion passes, and no closure exists. Analysis alone cannot satisfy readiness, and a later failure from a different actor remains visible. Evidence is still caller supplied; `ready` does not independently establish that combined behavior was exercised. Inspect the current check and closure result; do not equate recording a lesson with approval or actual integration. `resume` reconstructs retained responsibilities and adaptation state for a successor rather than starting a worker.

## Freshness and interpretation

The ledger pins proposal inputs and `candidate_scopes`, the union of intention read/write scopes and affected charter scopes. It also pins `source_digest` across that whole surface in the baseline workspace, including scopes outside the originating intention. A fresh check re-observes the relevant charters, baseline source surface, and candidate surface. Include all inputs needed for the claimed composition in those scopes. Unscoped files are not checked. Directory scopes include generated and hidden files; finish the composition before collecting final responses, and avoid writing scoped generated files between checks. Independent agents can use one shared composition directory with disjoint ownership, but must not describe it as independent isolated copies.

The ledger is an opt-in extension of the coordinator's local SQLite state. Its actor labels, peer decisions, evidence summaries, and outcomes are cooperative assertions. It supplies no authentication, automatic testing, scheduling, merge/apply operation, or authority grant. Check command results and their evidence boundaries rather than treating a zero exit status as proof that a capability works.
