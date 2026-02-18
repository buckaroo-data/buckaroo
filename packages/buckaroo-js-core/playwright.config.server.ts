import { defineConfig, devices } from '@playwright/test';

const PORT = 8701;

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['server.spec.ts'],
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
  timeout: 30_000,

  projects: [
    {
      name: 'chromium-server',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: `uv run python -m buckaroo.server --no-browser --port ${PORT}`,
    cwd: '../..',
    url: `http://localhost:${PORT}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },
});
