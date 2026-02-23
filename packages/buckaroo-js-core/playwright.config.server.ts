import { defineConfig, devices } from '@playwright/test';

const PORT = 8701;

// Allow overriding the Python used to start the server.
// In CI this points at a clean venv that only has buckaroo[mcp] installed.
const PYTHON = process.env.BUCKAROO_SERVER_PYTHON ?? 'uv run python';

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['server.spec.ts', 'server-buckaroo-search.spec.ts', 'server-buckaroo-summary.spec.ts', 'theme-screenshots-server.spec.ts', 'server-standalone-layout.spec.ts'],
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
    command: `${PYTHON} -m buckaroo.server --no-browser --port ${PORT}`,
    cwd: '../..',
    url: `http://localhost:${PORT}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },
});
