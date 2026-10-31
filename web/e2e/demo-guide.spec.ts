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
  await page.goto("./");
  await page.locator("[name=token]").waitFor();
  const dialog = page.getByRole("dialog", { name: /how to use the forge/i });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "This Pages build" })).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Try the demo flow" }),
  ).toBeVisible();
  await expect(dialog.getByText("python -m synbios init")).toBeVisible();
  await expect(dialog.getByText("Review release readiness")).toBeVisible();
  await expect(
    dialog.getByText("no separate", { exact: false }),
  ).toBeVisible();
});
