import { test, expect, login, openTask, save } from "./fixture";

test("real lifecycle ends with independent human acceptance of the exact candidate", async ({
  page,
  workspace,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  await login(page, workspace);
  await page.getByRole("button", { name: "Create task", exact: true }).click();
  await page.locator("[name=project_id]").selectOption({ index: 1 });
  await page.locator("[name=title]").fill("Browser lifecycle task");
  await page
    .locator("textarea[name=description]")
    .fill("Synthetic browser fixture; no external test execution.");
  await page
    .locator("[name=criteria]")
    .fill("Exact artifact binding\nIndependent review");
  await page.locator("[name=scope]").fill("web/");
  await save(page);
  await openTask(page, "Browser lifecycle task");
  await page.getByRole("button", { name: "Claim task", exact: true }).click();
  await page.getByRole("button", { name: "Start work", exact: true }).click();
  await page.getByRole("button", { name: "Add artifact", exact: true }).click();
  await page.locator("[name=title]").fill("Synthetic document");
  await page.locator("[name=kind]").selectOption("document");
  await page.locator("[name=revision]").fill("a".repeat(64));
  await page.locator("[name=digest]").fill("a".repeat(64));
  await page.locator("[name=summary]").fill("Synthetic browser test artifact");
  await save(page);
  await page.getByRole("button", { name: "Add evidence", exact: true }).click();
  await page
    .locator("[name=command]")
    .fill("SYNTHETIC fixture, no command executed");
  await page
    .locator("[name=summary]")
    .fill("Synthetic evidence for browser acceptance only");
  await page.locator("[name=tool]").fill("browser-fixture");
  await page.locator("[name=tool_version]").fill("1");
  await save(page);
  await page
    .getByRole("button", { name: "Submit for review", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByText("in review", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close task" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.locator("[name=token]")).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("synbios.token")),
  ).toBeNull();
  await login(page, workspace, true);
  await openTask(page, "Browser lifecycle task");
  await page
    .getByRole("button", { name: "Review candidate", exact: true })
    .click();
  await page
    .locator("[name=comment]")
    .fill("Independent synthetic fixture review of exact candidate.");
  await save(page);
  await expect(
    page.getByRole("dialog").getByText("accepted", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile board and task details fit a narrow viewport", async ({
  page,
  workspace,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, workspace);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await openTask(page, "Build evidence intake");
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("revoked credentials clear workspace and local credential on refresh", async ({
  page,
  workspace,
}) => {
  await login(page, workspace, true);
  const response = await fetch(
    workspace.url + "/api/commands/principal.revoke",
    {
      method: "POST",
      headers: {
        Authorization: "Bearer " + workspace.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ principal_id: workspace.reviewer.id }),
    },
  );
  expect(response.status).toBe(200);
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await expect(page.locator("[name=token]")).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("synbios.token")),
  ).toBeNull();
  await expect(
    page.getByRole("heading", { name: "The forge.", exact: true }),
  ).toHaveCount(0);
});

test("an in-flight refresh cannot restore a signed-out workspace", async ({
  page,
  workspace,
}) => {
  await login(page, workspace);
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
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await requested;
  await page.getByRole("button", { name: "Sign out" }).click();
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
    page.getByRole("heading", { name: "The forge.", exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(() => sessionStorage.getItem("synbios.token")),
  ).toBeNull();
});
