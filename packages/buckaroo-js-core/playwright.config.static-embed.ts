import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8766;
const STATIC_DIR = path.resolve(__dirname, '../../buckaroo/static');

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['static-embed.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
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
      name: 'chromium-static-embed',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: `npx --yes serve -l ${PORT} ${STATIC_DIR} --no-clipboard`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },
});
