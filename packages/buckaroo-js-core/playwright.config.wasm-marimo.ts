import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8765;
const WASM_DIR = path.resolve(__dirname, '../../docs/extra-html/example_notebooks/buckaroo_ddd_tour');

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['wasm-marimo.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
    ...devices['Desktop Chrome'],
  },
  // Longer timeout for WASM: Pyodide initialization can be slow (15-30s)
  timeout: 120_000,

  projects: [
    {
      name: 'chromium-wasm-marimo',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: `python3 -m http.server ${PORT} --directory ${WASM_DIR}`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
