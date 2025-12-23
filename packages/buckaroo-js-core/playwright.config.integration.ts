import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './pw-tests',
  // Match JupyterLab-based tests (integration, batch, and infinite scroll)
  testMatch: ['integration.spec.ts', 'integration-batch.spec.ts', 'infinite-scroll-transcript.spec.ts'],
  fullyParallel: false, // Integration tests should run serially
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Only one worker for integration tests
  reporter: 'html',
  use: {
    trace: 'off',
    actionTimeout: 10000,
    navigationTimeout: 15000,
    storageState: undefined,
    launchOptions: {
      args: ['--incognito'],
    },
  },
  timeout: 30000, // 30s per test

  projects: [
    {
      name: 'chromium-integration',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // JupyterLab is started by the shell script, not by Playwright
});
