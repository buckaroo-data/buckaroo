import { defineConfig, devices } from '@playwright/test';

const PORT = 2718;

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['marimo.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
    ...devices['Desktop Chrome'],
  },
  timeout: 60_000,

  projects: [
    {
      name: 'chromium-marimo',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: `uv run marimo run --headless --port ${PORT} --no-token tests/notebooks/marimo_pw_test.py`,
    cwd: '../..',
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
