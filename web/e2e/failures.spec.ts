import { test, expect, login, openTask, dismissGuideIfOpen } from "./fixture";

test("a rejected credential is reported on sign-in", async ({
  page,
  workspace,
}) => {
  await page.goto(workspace.url);
  await page.locator("[name=token]").waitFor();
  await dismissGuideIfOpen(page);
  await page.locator("[name=token]").fill("not-a-valid-credential");
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid credential");
  await expect(page.locator("[name=token]")).toBeVisible();
});

test("a failed integrity check replaces the intact-record indicator", async ({
  page,
  workspace,
}) => {
  await login(page, workspace);
  await expect(page.getByText("Record intact")).toBeVisible();
  // The server answers 409 instead of state when the audit chain fails.
  await page.route("**/api/state", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: "Store integrity failure: State does not match audit",
      }),
    }),
  );
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Store integrity failure",
  );
  await expect(page.getByText("Integrity alert")).toBeVisible();
  await expect(page.getByText("Record intact")).toHaveCount(0);
});

test("a failed bundle verification is an alert, not a success notice", async ({
  page,
  workspace,
}) => {
  await login(page, workspace);
  await page.getByRole("button", { name: "Provenance" }).click();
  await page.getByRole("button", { name: "Verify a bundle" }).click();
  await page
    .locator("[name=bundle]")
    .fill(JSON.stringify({ version: 1, format: "synbios-task" }));
  await page.getByRole("button", { name: "Verify bundle" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Bundle verification failed",
  );
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("a cancelled task is closed once, not accepted", async ({
  page,
  workspace,
}) => {
  await login(page, workspace);
  const commands: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/commands/")) commands.push(request.url());
  });
  await openTask(page, "Review release readiness");
  await page
    .getByRole("button", { name: "Cancel task", exact: true })
    .dblclick();
  await expect(
    page.getByRole("dialog").getByText("cancelled", { exact: true }),
  ).toBeVisible();
  expect(commands).toHaveLength(1);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "Close task" }).click();
  const closed = page
    .locator(".column")
    .filter({ has: page.getByRole("heading", { name: /^Closed/ }) });
  await expect(
    closed.getByRole("heading", { name: "Review release readiness" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Accepted/ })).toHaveCount(0);
});
