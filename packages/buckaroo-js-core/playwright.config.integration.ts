import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './pw-tests',
  testMatch: 'integration.spec.ts',
  fullyParallel: false, // Integration tests should run serially
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Only one worker for integration tests
  reporter: 'html',
  use: {
    trace: 'on-first-retry',
    // Timeouts for integration tests (increased for CI)
    actionTimeout: 30000,
    navigationTimeout: 60000,
    timeout: 120000, // Test timeout - 2 minutes for CI
  },

  projects: [
    {
      name: 'chromium-integration',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // JupyterLab is started by the shell script, not by Playwright
});
