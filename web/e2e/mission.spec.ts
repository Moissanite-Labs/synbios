import { test as base, expect, type Page } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

// Briefs contain disposable task credentials. Do not attach DOM snapshots on failure.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";

type MissionWorkspace = { url: string; token: string };
type TaskRecord = {
  id: string;
  title: string;
  revision: number;
  assignee_id: string | null;
  decisions: Array<{ id: string; status: string; choice?: string }>;
};
type State = {
  tasks: TaskRecord[];
  projects: Array<{ id: string; name: string }>;
  principals: Array<{ id: string; name: string }>;
};
const repository = resolve(fileURLToPath(new URL("../..", import.meta.url)));

// A genuinely empty persistent local store: onboarding is not tested against
// pre-populated fiction. Ephemeral credentials remain in child pipes/memory.
const test = base.extend<{ missionWorkspace: MissionWorkspace }>({
  missionWorkspace: async ({}, use) => {
    const directory = await mkdtemp(join(tmpdir(), "synbios-mission-e2e-"));
    const child = spawn(
      process.env.PYTHON || "python3",
      [
        "-u",
        "-c",
        `
import json, sys
from synbios.store import Store
from synbios.server import create_server
store = Store(sys.argv[1])
record = store.bootstrap('Mission operator')
store.close()
server = create_server(sys.argv[1], port=0)
record['url'] = 'http://127.0.0.1:' + str(server.server_port)
print(json.dumps(record), flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
`,
        join(directory, "mission.db"),
      ],
      { cwd: repository, stdio: ["ignore", "pipe", "pipe"] },
    );
    const lines = createInterface({ input: child.stdout });
    let stderr = "";
    child.stderr.on("data", (chunk) => (stderr += String(chunk)));
    try {
      const workspace = await new Promise<MissionWorkspace>(
        (resolve, reject) => {
          const timeout = setTimeout(
            () => reject(new Error("Mission fixture server did not start")),
            15_000,
          );
          lines.once("line", (line) => {
            clearTimeout(timeout);
            try {
              resolve(JSON.parse(line));
            } catch {
              reject(new Error("Invalid mission fixture startup response"));
            }
          });
          child.once("error", () => {
            clearTimeout(timeout);
            reject(new Error("Cannot start Python mission fixture"));
          });
          child.once("exit", (code) => {
            clearTimeout(timeout);
            reject(
              new Error(
                `Mission fixture exited (${code}): ${stderr.slice(-1000)}`,
              ),
            );
          });
        },
      );
      await use(workspace);
    } finally {
      lines.close();
      if (child.exitCode === null) {
        const exited = new Promise<void>((done) =>
          child.once("exit", () => done()),
        );
        child.kill("SIGTERM");
        await Promise.race([
          exited,
          new Promise<void>((done) => setTimeout(done, 3000)),
        ]);
        if (child.exitCode === null) child.kill("SIGKILL");
      }
      await rm(directory, { recursive: true, force: true });
    }
  },
});

async function state(
  workspace: MissionWorkspace,
  token = workspace.token,
): Promise<State> {
  const response = await fetch(workspace.url + "/api/state", {
    headers: { Authorization: "Bearer " + token },
  });
  if (!response.ok)
    throw new Error(`State request rejected (${response.status})`);
  return response.json();
}

async function command(
  workspace: MissionWorkspace,
  action: string,
  payload: Record<string, unknown>,
  token = workspace.token,
) {
  return fetch(workspace.url + "/api/commands/" + action, {
    method: "POST",
    headers: {
      Authorization: "Bearer " + token,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

async function login(page: Page, workspace: MissionWorkspace) {
  await page.goto(workspace.url);
  await page.locator("[name=token]").waitFor();
  await page.evaluate((token) => {
    const input = document.querySelector<HTMLInputElement>("[name=token]");
    if (!input) throw new Error("Credential input missing");
    input.value = token;
  }, workspace.token);
  await page
    .getByRole("button", { name: "Open workspace", exact: true })
    .click();
}

async function createMission(page: Page) {
  await page
    .getByRole("button", { name: "Create mission", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Mission name", { exact: true })
    .fill("Exo collaboration");
  await dialog
    .getByLabel("Desired outcome", { exact: true })
    .fill(
      "Agents improve Exo together while every assignment and real decision stays visible.",
    );
  await dialog
    .getByRole("button", { name: "Create mission", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /^Exo collaboration/ }),
  ).toBeVisible();
}

async function createSlice(
  page: Page,
  title = "Make Exo startup understandable",
) {
  await page
    .getByRole("button", { name: "Add work slice", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title", { exact: true }).fill(title);
  await dialog
    .getByLabel("Outcome", { exact: true })
    .fill("Explain startup state and the next useful action.");
  await dialog
    .getByLabel(/^Acceptance criteria/)
    .fill("Shows actual startup state\nReports unavailable telemetry honestly");
  await dialog.getByText("Scope and connections", { exact: true }).click();
  await dialog.getByLabel(/^Work scope/).fill("desktop/startup/");
  await dialog
    .getByRole("combobox", { name: "Stage", exact: true })
    .selectOption("prototype");
  await dialog
    .getByRole("button", { name: "Create work slice", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
}

test("a mission becomes an agent assignment, reported work, and a real human decision", async ({
  page,
  missionWorkspace: workspace,
}) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      !request.url().startsWith(workspace.url + "/")
    )
      external.push(new URL(request.url()).origin);
  });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          (window as unknown as { copiedBrief: string }).copiedBrief = value;
        },
      },
    });
  });
  await login(page, workspace);
  await createMission(page);
  await createSlice(page);
  await expect(
    page.getByText("Runtime and cost telemetry unavailable", { exact: false }),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Delegate to agent", exact: true })
    .click();
  const delegate = page.getByRole("dialog");
  await delegate
    .getByLabel("Agent name", { exact: true })
    .fill("Codex startup worker");
  const delegatedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/commands/task.delegate") &&
      response.request().method() === "POST",
    { timeout: 10000 },
  );
  await delegate
    .getByRole("button", { name: "Create agent brief", exact: true })
    .click();
  const response = await test.step("receive enrollment response", () =>
    delegatedResponse);
  expect(response.status()).toBe(200);
  const delegated = await test.step("read scoped enrollment credential", () =>
    response.json());
  // Never print or attach the one-time credential to a test artifact.
  expect(
    typeof delegated.token === "string" && delegated.token.length > 20,
  ).toBe(true);
  await test.step("copy agent brief", async () => {
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Copy task prompt", exact: true })
      .click({ timeout: 10000 });
  });
  const briefValid = await page.evaluate((operatorToken) => {
    const brief =
      (window as unknown as { copiedBrief: string }).copiedBrief || "";
    return (
      brief.includes("Make Exo startup understandable") &&
      brief.includes("desktop/startup/") &&
      !brief.includes(operatorToken)
    );
  }, workspace.token);
  expect(briefValid).toBe(true);
  await test.step("close copied brief", () => page.keyboard.press("Escape"));

  let task = (await state(workspace)).tasks[0];
  const report = await command(
    workspace,
    "task.report",
    {
      task_id: task.id,
      expected_revision: task.revision,
      summary:
        "Startup copy is implemented; awaiting the product wording decision.",
      progress: 65,
    },
    delegated.token,
  );
  expect(report.status).toBe(200);
  task = (await state(workspace)).tasks[0];
  const decision = await command(
    workspace,
    "decision.create",
    {
      task_id: task.id,
      expected_revision: task.revision,
      title: "Choose startup wording",
      question:
        "Should the first screen describe the current work or the available tools?",
      options: ["Lead with current work", "Lead with tools"],
    },
    delegated.token,
  );
  expect(decision.status).toBe(200);
  await page
    .getByRole("button", { name: "Refresh workspace", exact: true })
    .click();
  await expect(
    page
      .getByText(
        "Startup copy is implemented; awaiting the product wording decision.",
        { exact: true },
      )
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Choose startup wording", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Lead with current work", exact: true })
    .click();
  await expect
    .poll(async () => (await state(workspace)).tasks[0].decisions[0].status)
    .toBe("resolved");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: /^Exo collaboration/ }),
  ).toBeVisible();
  expect((await state(workspace)).tasks[0].decisions[0].choice).toBe(
    "Lead with current work",
  );
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("stale concurrent redirection is rejected and an old worker loses write authority", async ({
  page,
  missionWorkspace: workspace,
}) => {
  await login(page, workspace);
  await createMission(page);
  await createSlice(page);
  const task = (await state(workspace)).tasks[0];
  const first = await command(workspace, "task.delegate", {
    task_id: task.id,
    expected_revision: task.revision,
    name: "Original worker",
  });
  expect(first.status).toBe(200);
  const former = await first.json();
  const before = (await state(workspace)).tasks[0];
  const results = await Promise.all([
    command(workspace, "task.update", {
      task_id: before.id,
      expected_revision: before.revision,
      description: "Keep the UI outcome visible",
    }),
    command(workspace, "task.update", {
      task_id: before.id,
      expected_revision: before.revision,
      description: "Keep dependency blockers visible",
    }),
  ]);
  expect(results.map((result) => result.status).sort()).toEqual([200, 409]);
  const current = (await state(workspace)).tasks[0];
  const next = await command(workspace, "task.delegate", {
    task_id: current.id,
    expected_revision: current.revision,
    name: "Replacement worker",
  });
  expect(next.status).toBe(200);
  const reassigned = (await state(workspace)).tasks[0];
  const rejected = await command(
    workspace,
    "task.report",
    {
      task_id: reassigned.id,
      expected_revision: reassigned.revision,
      summary: "Late result from old assignment",
      progress: 99,
    },
    former.token,
  );
  expect(rejected.status).toBe(403);
  const rejectedLegacy = await command(
    workspace,
    "artifact.add",
    {
      task_id: reassigned.id,
      title: "Stale artifact",
      kind: "document",
      revision: "a".repeat(64),
      digest: "a".repeat(64),
    },
    former.token,
  );
  expect(rejectedLegacy.status).toBe(403);
  await page
    .getByRole("button", { name: "Refresh workspace", exact: true })
    .click();
  await expect(
    page.getByText("Replacement worker", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Late result from old assignment", { exact: true }),
  ).toHaveCount(0);
});

test("the original crystal geometry remains usable by keyboard on narrow screens", async ({
  page,
  missionWorkspace: workspace,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await login(page, workspace);
  await createMission(page);
  await createSlice(
    page,
    "A deliberately long task name that remains readable on a small phone screen",
  );
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const lattice = page.locator('svg[viewBox="-204 -184 408 368"]');
    await expect(lattice).toBeVisible();
    const node = lattice.locator('[role="button"]').first();
    await node.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("heading", {
        name: "A deliberately long task name that remains readable on a small phone screen",
        exact: true,
      }),
    ).toBeVisible();
  }
});

test("a coordinator plans only its mission and invalid plans leave no partial slices", async ({
  missionWorkspace: workspace,
}) => {
  const create = async (name: string) => {
    const response = await command(workspace, "project.create", {
      name,
      description: "Synthetic browser acceptance mission",
    });
    expect(response.status).toBe(200);
    return response.json();
  };
  const ownMission = await create("Coordinator's mission");
  const otherMission = await create("Separate mission");
  const enrollment = await command(workspace, "coordinator.enroll", {
    project_id: ownMission.id,
    name: "Scoped planner",
  });
  expect(enrollment.status).toBe(200);
  const coordinator = await enrollment.json();
  const slice = {
    key: "shape",
    title: "Agree the approach",
    description: "A bounded shape task",
    criteria: ["Approach is recorded"],
    scope: ["docs/"],
    stage: "shape",
    dependencies: [],
  };
  const denied = await command(
    workspace,
    "plan.create",
    { project_id: otherMission.id, tasks: [slice] },
    coordinator.token,
  );
  expect(denied.status).toBe(403);
  const invalid = await command(
    workspace,
    "plan.create",
    {
      project_id: ownMission.id,
      tasks: [slice, { ...slice, title: "Duplicate key" }],
    },
    coordinator.token,
  );
  expect(invalid.status).toBe(400);
  expect((await state(workspace)).tasks).toHaveLength(0);
  const planned = await command(
    workspace,
    "plan.create",
    {
      project_id: ownMission.id,
      tasks: [
        slice,
        {
          ...slice,
          key: "build",
          title: "Build the agreed behavior",
          stage: "build",
          dependencies: ["shape"],
        },
      ],
    },
    coordinator.token,
  );
  expect(planned.status).toBe(200);
  const records = (await state(workspace)).tasks;
  expect(records).toHaveLength(2);
  // Every atomically planned slice must also be independently exportable.
  for (const task of records) {
    const exported = await fetch(
      workspace.url + "/api/tasks/" + task.id + "/export",
      { headers: { Authorization: "Bearer " + workspace.token } },
    );
    expect(exported.status).toBe(200);
    const bundle = await exported.json();
    const verified = await fetch(workspace.url + "/api/bundles/verify", {
      method: "POST",
      headers: {
        Authorization: "Bearer " + workspace.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(bundle),
    });
    expect(verified.status).toBe(200);
    expect((await verified.json()).valid).toBe(true);
    expect(JSON.stringify(bundle).includes(coordinator.token)).toBe(false);
  }
});

test("an older mission refresh cannot resurrect a signed-out session", async ({
  page,
  missionWorkspace: workspace,
}) => {
  await login(page, workspace);
  await createMission(page);
  let release!: () => void;
  let started!: () => void;
  const held = new Promise<void>((done) => {
    release = done;
  });
  const requested = new Promise<void>((done) => {
    started = done;
  });
  await page.route("**/api/state", async (route) => {
    const response = await route.fetch();
    started();
    await held;
    await route.fulfill({ response });
  });
  const delivered = page.waitForResponse((response) =>
    response.url().endsWith("/api/state"),
  );
  await page
    .getByRole("button", { name: "Refresh workspace", exact: true })
    .click();
  await requested;
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  release();
  await (await delivered).finished();
  await page.evaluate(
    () =>
      new Promise<void>((done) =>
        requestAnimationFrame(() => requestAnimationFrame(() => done())),
      ),
  );
  await expect(page.locator("[name=token]")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /^Exo collaboration/ }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(() => sessionStorage.getItem("synbios.token")),
  ).toBeNull();
});

test("polling cannot silently rebase an open redirection form onto changed work", async ({
  page,
  missionWorkspace: workspace,
}) => {
  await login(page, workspace);
  await createMission(page);
  await createSlice(page);
  await page
    .getByRole("button", { name: "Redirect work", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Outcome", { exact: true })
    .fill("My unsaved old direction");
  const original = (await state(workspace)).tasks[0];
  const freshObserved = page.waitForResponse(async (response) => {
    if (!response.url().endsWith("/api/state") || response.status() !== 200)
      return false;
    const snapshot = await response.json();
    return snapshot.tasks.some(
      (task: { id: string; criteria: string[] }) =>
        task.id === original.id &&
        task.criteria.includes("Preserve the concurrent direction"),
    );
  });
  const redirected = await command(workspace, "task.update", {
    task_id: original.id,
    expected_revision: original.revision,
    description: "Another session's newly agreed direction",
    criteria: ["Preserve the concurrent direction"],
  });
  expect(redirected.status).toBe(200);
  await (await freshObserved).finished();
  await page.evaluate(
    () =>
      new Promise<void>((done) =>
        requestAnimationFrame(() => requestAnimationFrame(() => done())),
      ),
  );
  await dialog
    .getByRole("button", { name: "Save direction", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Work changed since you opened it",
  );
  const latest = (await state(workspace)).tasks[0] as TaskRecord & {
    description: string;
    criteria: string[];
  };
  expect(latest.description).toBe("Another session's newly agreed direction");
  expect(latest.criteria).toEqual(["Preserve the concurrent direction"]);
});

test("the mission interface records exact result evidence and independent acceptance", async ({
  page,
  missionWorkspace: workspace,
}) => {
  await login(page, workspace);
  await createMission(page);
  await createSlice(page);
  const task = (await state(workspace)).tasks[0];
  const delegation = await command(workspace, "task.delegate", {
    task_id: task.id,
    expected_revision: task.revision,
    name: "Result author",
  });
  expect(delegation.status).toBe(200);
  const worker = await delegation.json();
  expect(
    (
      await command(
        workspace,
        "task.transition",
        { task_id: task.id, status: "in_progress" },
        worker.token,
      )
    ).status,
  ).toBe(200);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await login(page, { ...workspace, token: worker.token });
  await page.getByText("Inspect work and evidence", { exact: true }).click();
  await page
    .getByRole("button", { name: "Attach a result", exact: true })
    .click();
  let dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Result title", { exact: true })
    .fill("Synthetic startup result");
  await dialog
    .getByRole("combobox", { name: "Result kind", exact: true })
    .selectOption("document");
  await dialog.getByLabel("Revision", { exact: true }).fill("a".repeat(64));
  await dialog
    .getByLabel("SHA-256 digest", { exact: true })
    .fill("a".repeat(64));
  await dialog
    .getByLabel("Summary", { exact: true })
    .fill("Synthetic artifact for browser acceptance. No source file changed.");
  await dialog
    .getByRole("button", { name: "Attach result", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Record test evidence", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("What was checked", { exact: true })
    .fill("Synthetic browser fixture evidence; no external command executed.");
  await dialog
    .getByLabel("Command run", { exact: true })
    .fill("SYNTHETIC fixture");
  await dialog.getByLabel("Tool", { exact: true }).fill("browser-fixture");
  await dialog.getByLabel("Tool version", { exact: true }).fill("1");
  await dialog
    .getByRole("button", { name: "Save evidence", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Submit for review", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve current result", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await login(page, workspace);
  await page
    .getByLabel("Review note", { exact: true })
    .fill(
      "Independent review of this synthetic result and its bound fixture evidence.",
    );
  await page
    .getByRole("button", { name: "Approve current result", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        ((await state(workspace)).tasks[0] as TaskRecord & { status: string })
          .status,
    )
    .toBe("accepted");
  await expect(
    page.getByRole("button", { name: "Delegate to agent", exact: true }),
  ).toHaveCount(0);
  const exported = await fetch(
    workspace.url + "/api/tasks/" + task.id + "/export",
    { headers: { Authorization: "Bearer " + workspace.token } },
  );
  const verified = await fetch(workspace.url + "/api/bundles/verify", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + workspace.token,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(await exported.json()),
  });
  expect((await verified.json()).valid).toBe(true);
});
