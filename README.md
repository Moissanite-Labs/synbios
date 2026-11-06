# Synbios

Synbios is a local mission control for people and agents working on a codebase. See the goal, how work is divided, who owns each piece, and which decisions need you. Give an agent a complete task brief, let it report back through the local API, and keep the result and its evidence together.

The main interface is the **Crystal Lattice merged** design selected in [Exofab #17](https://github.com/Moissanite-Labs/exofab/pull/17) and made interactive in [#20](https://github.com/Moissanite-Labs/exofab/pull/20). The lattice is the map of the mission: **Idea → Shape → Prototype → Build → Ship**. [Design provenance and mapping](docs/design/crystal-lattice.md).

**Status:** local reference implementation. Mission control uses a persistent SQLite store, authenticated HTTP API and CLI. Your own agent sessions do the work. Synbios does not start model sessions, run their tools, or apply their changes automatically.

## Start with your codebase

Requirements: Python 3.11+, Node.js 22+, npm; Git for capturing Git artifacts. Run the following from this checkout. The Python runtime uses the standard library; the checkout supplies the web assets.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm --prefix web ci
npm --prefix web run build
python -m synbios start --workspace /absolute/path/to/exo
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. Choose your actual Exo checkout or any existing folder; startup does not edit its source files.

Open the local URL printed in the terminal and enter the browser credential printed with it. Keep the terminal running. Repeat the same `start` command to return to the same workspace. The launcher keeps its database and private browser credential outside your codebase. [Local setup and daily workflow](docs/mission-control.md) explains paths, existing databases, multiple agent sessions and troubleshooting.

## Your first mission

1. Use **Edit mission** to give the mission a clear outcome. Add a work slice yourself, or enroll a coordinator and copy its brief to your preferred agent harness.
2. Inspect the proposed slices on the lattice. Each carries a purpose, acceptance criteria, scope and dependencies.
3. Assign a slice to an agent and copy its task brief. Enrollment assembles a one-time handoff with context, API instructions and the new scoped credential.
4. Keep this view open while agents report progress, blockers and results. Select a piece to inspect its sources or redirect the work.
5. Respond to actual decisions and review requests. Code changes, their test evidence and independent review remain connected through the existing artifact workflow.

Crew shows recorded work allocation. Progress reports are labeled as reports; they do not prove a session is currently running. Token use, cost and compute are unavailable until a harness supplies telemetry. A changed candidate is ordinary work, not by itself a reason to ask for human approval.

Select a piece and expand **Inspect work and evidence** to attach results, record tests or submit for review. The full record console and permission controls remain available at `?advanced=1`. Task approval records a decision about an exact artifact; it does not merge or deploy code.

## Try a separate demonstration

```sh
python -m synbios demo --db demo.db
python -m synbios serve --db demo.db
```

The command refuses an existing database and prints separate operator and reviewer credentials. All seeded tasks and evidence are synthetic. The static Pages demonstration also remains explicitly synthetic; use the local server for real coordination.

## Connect any local agent harness

Give each session its own identity and credential. A task credential can act only within its task grants; a coordinator enrollment gives authority to organize work in its named project. All authenticated identities can read the store, so use separate stores when projects must not share context.

The generated brief is the starting point for Codex, Claude Code, Gemini CLI or another harness that can call a local command or HTTP API. Discovery is at `/.well-known/synbios.json`; the authenticated API schema is at `/api/schema`.

```sh
# Use the scoped credential issued for this session, not the browser credential.
export SYNBIOS_TOKEN='your-agent-token'
python -m synbios state
# Delegation already claims the task for this session.
python -m synbios command task.transition --data '{"task_id":"TASK_ID","status":"in_progress"}'
python -m synbios capture --task TASK_ID --repo /path/to/clean/candidate
```

Use a separate candidate folder or Git worktree for each concurrent implementation. A task scope is a coordination agreement; it does not sandbox filesystem access. The [earlier local collaboration experiment](experiments/local-collaboration/README.md) retains its scope-conflict, stale-baseline and candidate-comparison tools. Its database is separate from mission control and is not automatically imported.

## Evidence and trust

A new artifact makes earlier evidence stale. Submission and approval require passing current test evidence, no current failures, and accepted dependencies. A human other than the artifact's author reviews it. Accepted tasks are sealed; revise through a successor task.

Test and progress records are reports from authenticated submitters. Synbios checks their bindings and permission rules, but does not independently execute the reported work. Its audit hash chain detects some local history changes; it is not a digital signature or a formal proof. The server is loopback-only.

See [the trust model](docs/trust-model.md), [mission-control contract](docs/mission-control.md), [artifact API contract](docs/implementation-contract.md), and [roadmap](docs/roadmap.md). The [founding vision](docs/vision.md) and [formal-verification RFC](docs/proof-evidence-rfc.md) describe further work.

## Development

```sh
python -m unittest discover -s tests -v
python -m synbios.shadow
npm --prefix web run check
npm --prefix web exec playwright install chromium
npm --prefix web run test:e2e
```

Use `npm --prefix web run dev` with the Python server for frontend development. Follow [the contribution guidance](CONTRIBUTING.md): exercise real forms against the server, test rejection cases, and obtain independent review. Local checks, native platform checks, hosted CI and deployment are separate evidence.

## SYM-3 (agent wire compression)

**SYM-3** is a tokenizer-aware wire format for forge lifecycle messages between agents (shared session lexicon, state deltas, content-addressed refs, adaptive encodings). The **protocol spec, paper, canonical benchmarks, and project site** live in **[aska-digital/protean-sym2p](https://github.com/aska-digital/protean-sym2p)** (**DOI:** pending). This repo holds the Synbios integration implementation and verified integration bench ([sym3-integration.md](docs/sym3-integration.md)).

Headline results on synthetic lifecycles (**o200k_base**, primary total = decode-sufficient setup min + messages; see [sym3-bench.md](docs/sym3-bench.md)):

| Transcript | Compact JSON | SYM-3 refs | SYM-3 adaptive |
| --- | ---: | ---: | ---: |
| 11 messages | 682 | **491** | 512 |
| 40 messages | 5343 | **1717** | 1738 |
| 200 messages | 27363 | **7628** | 7649 |

Savings depend on repeated content and shared state—they scale with conversation length, not single-turn prompts. On 11 messages, **full** lexicon setup (524 + messages) can exceed compact JSON. Do not compare against English lossy summaries for information equivalence.

**Model comprehension** on SYM-3 wire lines (decode accuracy, session questions, generation round-trip) is **pending**; see `synbios.sym3.comprehension` (not run in CI).

Reproduce locally: `make bench` after `pip install -r requirements-bench.txt` ([sym3-bench-reproduce.md](docs/sym3-bench-reproduce.md)).

The repository has not adopted a license. No license or economic rights are implied by recording a contribution.
