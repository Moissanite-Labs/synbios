import { test, expect } from "@playwright/test";

const GUIDE_STORAGE_KEY = "synbios.guide.v1.dismissed";

test.beforeEach(async ({ page }) => {
  await page.addInitScript((key) => {
    localStorage.removeItem(key);
  }, GUIDE_STORAGE_KEY);
});

test("pages demo guide shows demo callout and demo walkthrough", async ({
  page,
}) => {
  await page.goto("./?advanced=1");
  await page.locator("[name=token]").waitFor();
  const dialog = page.getByRole("dialog", { name: /how to use the forge/i });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "This Pages build" }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Try the demo flow" }),
  ).toBeVisible();
  await expect(dialog.getByText("python -m synbios init")).toBeVisible();
  await expect(dialog.getByText("Review release readiness")).toBeVisible();
  await expect(dialog.getByText("no separate", { exact: false })).toBeVisible();
});

test("Pages opens the chosen Crystal Lattice as an honest read-only example", async ({
  page,
}) => {
  const errors: string[] = [];
  const unexpected: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).hostname !== "127.0.0.1"
    )
      unexpected.push(new URL(request.url()).origin);
  });
  await page.goto("./");
  await page
    .getByRole("button", { name: "Explore example mission", exact: true })
    .click();
  await expect(page.locator('svg[viewBox="-204 -184 408 368"]')).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Crew", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Live work", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Trace", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add work slice", exact: true }).first(),
  ).toBeDisabled();
  await expect(
    page.getByText("Runtime and cost telemetry unavailable", { exact: false }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});
