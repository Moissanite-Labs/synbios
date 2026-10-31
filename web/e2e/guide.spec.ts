import { test, expect, login } from "./fixture";
import { devices } from "@playwright/test";

const GUIDE_STORAGE_KEY = "synbios.guide.v1.dismissed";

test("orientation guide opens on first visit and can be reopened", async ({
  page,
  workspace,
}) => {
  await page.addInitScript((key) => {
    localStorage.removeItem(key);
  }, GUIDE_STORAGE_KEY);
  await page.goto(workspace.url);
  await page.locator("[name=token]").waitFor();
  const dialog = page.getByRole("dialog", { name: /how to use the forge/i });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Walk through a task" }),
  ).toBeVisible();
  await expect(dialog.getByText("Try the demo flow")).toHaveCount(0);
  await page.getByRole("button", { name: "Got it", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(
    await page.evaluate(
      (key) => localStorage.getItem(key),
      GUIDE_STORAGE_KEY,
    ),
  ).toBe("1");
  await page.getByRole("button", { name: "Open guide", exact: true }).click();
  await expect(dialog).toBeVisible();
  await page.getByRole("button", { name: "Close guide", exact: true }).click();
  await expect(dialog).toHaveCount(0);
});

test("escape closes the orientation guide", async ({ page, workspace }) => {
  await page.addInitScript((key) => {
    localStorage.removeItem(key);
  }, GUIDE_STORAGE_KEY);
  await page.goto(workspace.url);
  await page.locator("[name=token]").waitFor();
  const dialog = page.getByRole("dialog", { name: /how to use the forge/i });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("got it stays visible on a phone-sized viewport", async ({
  page,
  workspace,
}) => {
  await page.setViewportSize(devices["iPhone SE"].viewport);
  await page.addInitScript((key) => {
    localStorage.removeItem(key);
  }, GUIDE_STORAGE_KEY);
  await page.goto(workspace.url);
  await page.locator("[name=token]").waitFor();
  const gotIt = page.getByRole("button", { name: "Got it", exact: true });
  await expect(gotIt).toBeVisible();
  await gotIt.scrollIntoViewIfNeeded();
  await expect(gotIt).toBeInViewport();
});

test("guide is available inside the workspace", async ({ page, workspace }) => {
  await page.addInitScript((key) => {
    localStorage.setItem(key, "1");
  }, GUIDE_STORAGE_KEY);
  await login(page, workspace);
  await page.getByRole("button", { name: "Open guide", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: /how to use the forge/i }),
  ).toBeVisible();
  await expect(page.getByText("What Synbios is")).toBeVisible();
});
