# Crystal Lattice local dashboard

A runnable, dependency-free interface to the shared `prototype/coordinator.py` backend. It reads actual SQLite records and re-observes scoped files. It has no embedded agents, fabricated activity, fixtures in normal operation, external requests, or automatic code application.

Requires Python 3.11+ with its standard SQLite support. Tested here on Linux; macOS and Windows are user test targets. Run from the `experiments/local-collaboration` folder. Keep the database **outside the observed target folder**, including outside its symlink-resolved location.

## Launch against an existing folder

```bash
python3 dashboard/server.py --db /absolute/path/outside-target/weave.sqlite --root /absolute/path/to/target --port 0
```

The database's parent folder must already exist. `--root` initializes a fresh database or verifies that an existing database belongs to that same target. It never seeds work or modifies target files. `--port 0` chooses a free loopback port. Open the printed `http://127.0.0.1:PORT/` URL; `localhost` is intentionally rejected by strict Host checking. Stop with Ctrl+C. Use `python` or `py -3` on Windows if that is the installed Python command.

Reopen an existing coordinator database:

```bash
python3 dashboard/server.py --db /absolute/path/outside-target/weave.sqlite --port 7343
```

The database may also be updated by the prototype CLI while the dashboard runs. The page refreshes every five seconds when visible and no form/control is focused; **Refresh observations** requests a fresh view immediately. Restarting the server changes its capability; reload the page to reconnect.

## Exercise the full local loop

1. Start with a scratch target containing `example.txt` and an external database, using the launch command above.
2. In **Names at the table**, register `worker-a`. In **Declare an intention**, enter that actor and a write path of `example.txt`. The record and its baseline appear immediately.
3. Declare a second actor's read intention for `example.txt`. The dashboard shows the actual `write/read` overlap and a dashed lattice connection.
4. Edit `example.txt` yourself in an editor and click **Refresh observations**. Both active records become **stale**, with the changed path listed. This external edit is the only target source mutation in this walkthrough.
5. Declare a replacement using the same actor name and **Replaces an active intention**. The new revision gets a fresh current baseline and the former record becomes superseded.
6. Preserve two named alternatives, associating each with an intention and an external location. Optional SHA-256 values are recorded as caller assertions. Select **accepted (advisory)** for one candidate. Reload the page; the selection persists.
7. Close an active intention as completed or abandoned. Its scopes no longer contribute conflicts. Completed is a declared lifecycle state, not evidence that tests passed.
8. Confirm the exact database records from a separate process:

```bash
python3 prototype/coordinator.py --db /absolute/path/outside-target/weave.sqlite status
```

The human decision circle is an interface legend; diamonds represent recorded intentions and do not imply live agents. Rings express no stage, progress, or dependency. The lattice shows the newest 48 intentions, with an explicit shown/total caption; the work list includes all records. The trace renders the latest 40 events; the underlying API and CLI retain all events.

## HTTP API

The server imports the Coordinator for every state operation and has no duplicate schema or merge/apply implementation. Each HTTP request uses its own SQLite connection. Replies use `{ "ok": true, "protocol": "weave.local.v1", "result": ... }`, except the session bootstrap described below. Errors use `{ "ok": false, "error": ... }`.

| Request | Body / result |
| --- | --- |
| `GET /api/session` | Send `X-Lattice-Bootstrap: 1`; returns `{ok, token, protocol}`. |
| `GET /api/status` | Full Coordinator status, including actors, intentions, conflicts, fresh observations, alternatives and events. |
| `POST /api/actors` | `{name}` → registered actor. |
| `POST /api/intentions` | `{actor, reads: [], writes: [], supersedes?: id}` → intention and overlaps. |
| `POST /api/intentions/finish` | `{id, status: "completed" or "abandoned"}` → updated intention. |
| `POST /api/alternatives` | `{intent_id, label, location, status?: "proposed", candidate_digest?: lowercase SHA-256}` → candidate. |
| `POST /api/alternatives/status` | `{id, status: "proposed", "testing", "accepted", or "rejected"}` → candidate selection. |

Send `X-Lattice-Token: TOKEN` for status and mutations. Every POST requires the exact `Origin: http://127.0.0.1:PORT`, `Content-Type: application/json`, and one valid Content-Length of 1–65536 bytes. Paths are arrays of at most 128 strings. Actor identities remain caller-asserted even with the session capability. The bootstrap capability is held only in page memory and never put in URLs, console logs, or browser storage.

## Boundaries

- The listener binds only IPv4 loopback `127.0.0.1`; Host must exactly match the printed host and port. Origins, when supplied, must match; all mutations require Origin. Cross-site Fetch Metadata and all preflight requests are rejected. No CORS headers are emitted.
- A random per-process capability protects the data API. Bootstrap requires a custom header that another web origin cannot send without a denied preflight. CSP blocks framing, external assets and inline script. This reduces browser-origin attacks; it does not authenticate local OS processes, protect against an already-compromised browser/origin, or assign harness identities. Any trusted local client that obtains the capability can perform all coordination operations.
- Static serving uses a three-path allowlist, and responses are not cached. HTTP logging is disabled so neither tokens nor caller input appear in request logs. Responses may expose the workspace path, names, scopes and recorded metadata to authorized local clients.
- SQLite is the shared coordination record. Scopes are cooperative declarations; they do not lock or sandbox external agents. Observations may race filesystem edits; symlink checks are not a complete hostile-filesystem sandbox. The event log is mutable and unsigned. A large folder or record history can make full status observations expensive; bounded mutation bodies do not bound database size or status response size. The stdlib HTTP service is a local prototype, not a hardened multi-user server.
- `accepted` is an advisory comparison state. Candidate locations and digests are caller-asserted and not read, validated against candidate content, executed, applied, merged, or bound to Synbios approval. There is no authenticated human identity or signed approval flow. Multiple candidates can be accepted because selections are independent labels.
- The current runtime does not launch models or integrate arbitrary live Codex, Claude, Grok, Gemini, Antigravity or other harnesses. Such harnesses can cooperate through the CLI/HTTP contract if explicitly adapted; a registered name does not establish an adapter. Formal verification, weight-level collaboration and FPGA integration are not implemented.

## Validation and visual provenance

```bash
python3 -m unittest discover -s dashboard -p 'test_*.py' -v
# Optional Node standard-library regression suite, also run in CI:
node --test dashboard/test_refresh.cjs
```

Eight HTTP integration tests use a real threaded listener and temporary SQLite database. They exercise actor registration, conflicting declarations, externally stale files, replacement baselines, candidate selection and close transitions; compare persistent state with a separate CLI process; verify target source content remains unchanged by HTTP mutations; and test Host/Origin/token/body rejection, bootstrap and static allowlisting. These are HTTP/backend tests, **not visual browser tests**, accessibility certification, formal verification, or macOS test results.

The plain HTML/CSS/JS composition follows the recorded [exoframe Crystal Lattice design SPEC](https://github.com/Moissanite-Labs/exoframe/blob/main/docs/design/public-intake/SPEC.md), linked as visual provenance: exact dark/silicon/carbon/ice palette, local font fallbacks, hex guide lattice, human circle, intention diamonds, panels for work/decisions/trace, and text-plus-shape statuses. This is a new local coordination surface inspired by that design, not the public-intake product or Synbios. No original JavaScript is copied. It has visible labels, keyboard-operable nodes, focus rings, a skip link, an error live region, responsive layout, no animation or remote fonts. Actual keyboard, screen-reader and visual browser acceptance remains for local user testing.
