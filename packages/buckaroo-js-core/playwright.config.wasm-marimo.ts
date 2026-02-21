import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8765;
const WASM_DIR = path.resolve(__dirname, '../../docs/extra-html/example_notebooks/buckaroo_simple');

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['wasm-marimo.spec.ts'],
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
  // Pyodide init can take 15-30s, plus widget render
  timeout: 60_000,

  projects: [
    {
      name: 'chromium-wasm-marimo',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: `npx --yes serve -l ${PORT} -s ${WASM_DIR} --no-clipboard`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
