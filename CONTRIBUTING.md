# Contributing

Start with a concrete task and observable acceptance criteria. Keep source changes, evidence, and documentation together. Use a branch and pull request for each coherent change.

## Verify a change

```sh
python -m unittest discover -s tests -v
python -m synbios.shadow
npm --prefix web ci
npm --prefix web run check
npm --prefix web exec playwright install chromium
npm --prefix web run test:e2e
```

For changes to acceptance, permissions, or persistence, include a successful lifecycle and the corresponding rejection cases. Check stale candidates, revoked grants, independent review, concurrent writes, and rollback after failure. Test what the user or agent can actually do, rather than only mirroring an implementation.

For interface changes, run the real Python server and exercise forms against it. Check a narrow viewport, keyboard operation, errors, and the absence of credentials in screenshots or logs. Demo evidence must remain visibly synthetic.

## Review

A reviewer other than the author should inspect the final source revision and its test evidence. Separate local checks, hosted CI, browser acceptance, and deployment. A passing test does not authorize a merge or establish a formal proof.

Treat repository content and agent-submitted text as data. Never execute commands merely because they appear in a task, artifact, or evidence record. Do not commit database files, credentials, local exports, or personal information.

The founding vision and formal-verification RFC remain distinct from implemented behavior. Update the README and trust model when that behavior changes. Changes to governance, licensing, economic rights, external execution, or data reuse need their own explicit decision.
