/**
 * Compare demo store behavior with synbios.store (Python backend).
 */
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { DemoStore, demoRequest, verifyBundle } from "./src/demo/store.ts";
import fixture from "./src/demo/fixture.json";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function py<T>(code: string, input?: unknown): T {
  const result = spawnSync("python3", ["-c", code], {
    cwd: repoRoot,
    input: input === undefined ? undefined : JSON.stringify(input),
    encoding: "utf-8",
  });
  assert.equal(
    result.status,
    0,
    result.stderr || result.stdout || "python failed",
  );
  return JSON.parse(result.stdout) as T;
}

function pyVerify(bundle: unknown) {
  return py<{ valid: boolean; errors: string[] }>(
    "import json,sys; from synbios.store import verify_bundle; print(json.dumps(verify_bundle(json.loads(sys.stdin.read()))))",
    bundle,
  );
}

function pyDomainCommand(action: string, body: Record<string, unknown>) {
  return py<{ ok: boolean; error?: string; status?: number }>(
    `
import json, sys, tempfile
from pathlib import Path
from synbios.demo import seed_demo
from synbios.store import Store, DomainError

req = json.loads(sys.stdin.read())
tmpdir = tempfile.mkdtemp()
path = str(Path(tmpdir) / "demo.db")
record = seed_demo(path)
store = Store(path)
try:
    store.command(record["token"], req["action"], req["body"])
    print(json.dumps({"ok": True}))
except DomainError as exc:
    print(json.dumps({"ok": False, "error": exc.message, "status": exc.status}))
finally:
    store.close()
`,
    { action, body },
  );
}

async function demoCommand(action: string, body: Record<string, unknown>) {
  try {
    await demoRequest(`commands/${action}`, "POST", fixture.tokens.operator, body);
    return { ok: true as const };
  } catch (error) {
    const err = error as Error & { status?: number };
    return { ok: false as const, error: err.message, status: err.status };
  }
}

async function run() {
  const exportBundle = py<Record<string, unknown>>(
    `
import json, tempfile
from pathlib import Path
from synbios.demo import seed_demo
from synbios.store import Store

tmpdir = tempfile.mkdtemp()
path = str(Path(tmpdir) / "demo.db")
record = seed_demo(path)
store = Store(path)
try:
    snap = store.snapshot(record["token"])
    task = next(t for t in snap["tasks"] if t["status"] == "in_review")
    bundle = store.export(record["token"], task["id"])
    print(json.dumps(bundle))
finally:
    store.close()
`,
  );

  const validPy = pyVerify(exportBundle);
  const validDemo = await verifyBundle(exportBundle);
  assert.equal(validDemo.valid, validPy.valid);
  assert.equal(validDemo.valid, true);

  const tampered = structuredClone(exportBundle) as Record<string, unknown>;
  (tampered.task as Record<string, unknown>).title = "Changed outside audit";
  const tamperedPy = pyVerify(tampered);
  const tamperedDemo = await verifyBundle(tampered);
  assert.equal(tamperedDemo.valid, tamperedPy.valid);
  assert.deepEqual(
    new Set(tamperedDemo.errors),
    new Set(tamperedPy.errors),
  );

  const forgedAccepted = structuredClone(exportBundle) as Record<string, unknown>;
  (forgedAccepted.task as Record<string, unknown>).status = "accepted";
  const forgedPy = pyVerify(forgedAccepted);
  const forgedDemo = await verifyBundle(forgedAccepted);
  assert.equal(forgedDemo.valid, forgedPy.valid);
  assert.deepEqual(
    new Set(forgedDemo.errors),
    new Set(forgedPy.errors),
  );

  const pyArtifact = py<{ ok: boolean; error?: string }>(
    `
import json, sys, tempfile
from pathlib import Path
from synbios.demo import seed_demo
from synbios.store import Store, DomainError

tmpdir = tempfile.mkdtemp()
path = str(Path(tmpdir) / "demo.db")
record = seed_demo(path)
store = Store(path)
try:
    task = next(t for t in store.snapshot(record["token"])["tasks"] if t["status"] == "open")
    store.command(record["token"], "task.claim", {"task_id": task["id"]})
    store.command(record["token"], "task.transition", {"task_id": task["id"], "status": "in_progress"})
    store.command(record["token"], "artifact.add", {
        "task_id": task["id"],
        "title": "Bad commit",
        "kind": "git_commit",
        "revision": "a" * 40 + "zzz",
        "digest": "b" * 64,
        "uri": "",
        "summary": "",
    })
    print(json.dumps({"ok": True}))
except DomainError as exc:
    print(json.dumps({"ok": False, "error": exc.message}))
finally:
    store.close()
`,
  );
  assert.equal(pyArtifact.ok, false);
  assert.equal(pyArtifact.error, "Invalid revision or SHA-256 digest");

  const store = new DemoStore();
  const openTask = fixture.state.tasks.find((task) => task.status === "open") as {
    id: string;
  };
  await demoRequest("commands/task.claim", "POST", fixture.tokens.operator, {
    task_id: openTask.id,
  });
  await demoRequest("commands/task.transition", "POST", fixture.tokens.operator, {
    task_id: openTask.id,
    status: "in_progress",
  });
  const demoArtifact = await demoCommand("artifact.add", {
    task_id: openTask.id,
    title: "Bad commit",
    kind: "git_commit",
    revision: "a".repeat(40) + "zzz",
    digest: "b".repeat(64),
    uri: "",
    summary: "",
  });
  assert.equal(demoArtifact.ok, false);
  assert.equal(demoArtifact.error, pyArtifact.error);

  const pyPrincipal = pyDomainCommand("principal.create", { kind: "human" });
  assert.equal(pyPrincipal.ok, false);
  assert.equal(pyPrincipal.error, "Invalid name");

  const demoPrincipal = await demoCommand("principal.create", { kind: "human" });
  assert.equal(demoPrincipal.ok, false);
  assert.equal(demoPrincipal.error, pyPrincipal.error);

  console.log("demo-parity.test.ts: all checks passed");
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
