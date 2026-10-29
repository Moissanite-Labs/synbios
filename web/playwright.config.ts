import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  reporter: "list",
  use: {
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    screenshot: "off",
    video: "off",
    ...(process.env.PLAYWRIGHT_CHANNEL
      ? { channel: process.env.PLAYWRIGHT_CHANNEL }
      : {}),
  },
});
