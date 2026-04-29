import { test, expect } from '@playwright/test';
import { waitForGrid } from './server-helpers';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const screenshotsDir = path.join(__dirname, '..', 'screenshots');

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

function writeTempCsv(): string {
  const header = 'name,age,score';
  const rows = [
    'Alice,30,88.5',
    'Bob,25,92.3',
    'Charlie,35,76.1',
    'Diana,28,95.0',
    'Eve,32,81.7',
  ];
  const content = [header, ...rows].join('\n') + '\n';
  const tmpPath = path.join(os.tmpdir(), `buckaroo_theme_${Date.now()}.csv`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test('server: theme config applied via /load', async ({ page, request }) => {
  const csvPath = writeTempCsv();
  const session = `theme-${Date.now()}`;
  const resp = await request.post(`${BASE}/load`, {
    data: {
      session,
      path: csvPath,
      component_config: {
        theme: {
          accentColor: '#ff6600',
          backgroundColor: '#1a1a2e',
          colorScheme: 'dark',
        },
      },
    },
  });
  expect(resp.ok()).toBeTruthy();

  await page.goto(`${BASE}/s/${session}`);
  await waitForGrid(page);

  // Assert background color on the grid
  const gridBody = page.locator('.ag-body-viewport').first();
  const bg = await gridBody.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(bg).toBe('rgb(26, 26, 46)'); // #1a1a2e

  await page.screenshot({
    path: path.join(screenshotsDir, 'server-theme-custom.png'),
    fullPage: true,
  });

  fs.unlinkSync(csvPath);
});

test('server: no theme = default rendering', async ({ page, request }) => {
  const csvPath = writeTempCsv();
  const session = `no-theme-${Date.now()}`;
  const resp = await request.post(`${BASE}/load`, {
    data: { session, path: csvPath },
  });
  expect(resp.ok()).toBeTruthy();

  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto(`${BASE}/s/${session}`);
  await waitForGrid(page);

  const gridBody = page.locator('.ag-body-viewport').first();
  const bg = await gridBody.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(bg).toBe('rgb(255, 255, 255)');

  fs.unlinkSync(csvPath);
});
