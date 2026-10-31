import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  reporter: "list",
  use: {
    headless: true,
    viewport: { width: 1440, height: 1000 },
    baseURL: "http://127.0.0.1:4173/synbios/",
    trace: "off",
    screenshot: "off",
    video: "off",
    ...(process.env.PLAYWRIGHT_CHANNEL
      ? { channel: process.env.PLAYWRIGHT_CHANNEL }
      : {}),
  },
  webServer: {
    command: "npm run preview:pages",
    url: "http://127.0.0.1:4173/synbios/",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
