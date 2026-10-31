import { test as base, expect, type Page } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
export { expect };
export type Workspace = {
  url: string;
  token: string;
  reviewer_token: string;
  reviewer: { id: string };
};
const repository = resolve(fileURLToPath(new URL("../..", import.meta.url)));
export const test = base.extend<{ workspace: Workspace }>({
  workspace: async ({}, use) => {
    const directory = await mkdtemp(join(tmpdir(), "synbios-e2e-"));
    // Credentials stay in a private child pipe and fixture memory, never artifacts.
    const child = spawn(
      process.env.PYTHON || "python3",
      [
        "-u",
        "-c",
        `
import json, sys
from synbios.demo import seed_demo
from synbios.server import create_server
record = seed_demo(sys.argv[1])
server = create_server(sys.argv[1], port=0)
record['url'] = 'http://127.0.0.1:' + str(server.server_port)
print(json.dumps(record), flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
`,
        join(directory, "fixture.db"),
      ],
      { cwd: repository, stdio: ["ignore", "pipe", "pipe"] },
    );
    const lines = createInterface({ input: child.stdout });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    try {
      const workspace = await new Promise<Workspace>((fulfil, reject) => {
        const timeout = setTimeout(
          () => reject(new Error("Local fixture server did not start")),
          15_000,
        );
        lines.once("line", (line) => {
          clearTimeout(timeout);
          try {
            fulfil(JSON.parse(line));
          } catch {
            reject(new Error("Invalid fixture startup response"));
          }
        });
        child.once("error", () => {
          clearTimeout(timeout);
          reject(new Error("Cannot start Python fixture"));
        });
        child.once("exit", (code) => {
          clearTimeout(timeout);
          reject(
            new Error(
              `Python fixture exited (${code}): ${stderr.slice(-1000)}`,
            ),
          );
        });
      });
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
export async function dismissGuideIfOpen(page: Page) {
  const dismiss = page.getByRole("button", { name: "Got it", exact: true });
  if (await dismiss.isVisible().catch(() => false)) {
    await dismiss.click();
  }
}
export async function login(
  page: Page,
  workspace: Workspace,
  reviewer = false,
) {
  await page.goto(workspace.url);
  const tokenInput = page.locator("[name=token]");
  await tokenInput.waitFor();
  await dismissGuideIfOpen(page);
  await tokenInput.fill(
    reviewer ? workspace.reviewer_token : workspace.token,
  );
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "The forge.", exact: true }),
  ).toBeVisible();
}
export async function openTask(page: Page, title: string) {
  await page
    .getByRole("button")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) })
    .click();
}
export async function save(page: Page) {
  await page
    .getByRole("button", { name: "Save to record", exact: true })
    .click();
}
