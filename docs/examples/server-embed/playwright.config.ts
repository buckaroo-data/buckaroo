import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./pw-tests",
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "line" : "html",
  timeout: 60_000,
  globalSetup: "./pw-tests/global-setup.ts",
  globalTeardown: "./pw-tests/global-teardown.ts",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // The Buckaroo server is started by global-setup.ts (see comment there).
  // Vite stays in webServer because Playwright handles a Node dev server fine.
  webServer: {
    command: "pnpm dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
