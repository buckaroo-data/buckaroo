import { test } from '@playwright/test';
import { loadSession, waitForGrid } from './server-helpers';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

const SCHEMES = ['light', 'dark'] as const;

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

// ---------- test data --------------------------------------------------------

function writeTempCsv(rowCount: number): string {
  const header = 'name,age,score';
  const rows = [];
  for (let i = 0; i < rowCount; i++) {
    rows.push(`row${i},${20 + (i % 50)},${(i * 1.7).toFixed(1)}`);
  }
  const content = [header, ...rows].join('\n') + '\n';
  const tmpPath = path.join(os.tmpdir(), `buckaroo_screenshot_${Date.now()}_${rowCount}.csv`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

function cleanupFile(p: string) {
  if (p && fs.existsSync(p)) fs.unlinkSync(p);
}

async function loadDefault(request: any, session: string, filePath: string) {
  const resp = await request.post(`${BASE}/load`, {
    data: { session, path: filePath },
  });
  if (!resp.ok()) throw new Error(`/load failed (${resp.status()}): ${await resp.text()}`);
  return resp.json();
}

async function loadBuckaroo(request: any, session: string, filePath: string) {
  const resp = await request.post(`${BASE}/load`, {
    data: { session, path: filePath, mode: 'buckaroo' },
  });
  if (!resp.ok()) throw new Error(`/load failed (${resp.status()}): ${await resp.text()}`);
  return resp.json();
}

// ---------- screenshots: default viewer mode ---------------------------------

test.describe('Server theme screenshots', () => {
  let csv5: string;
  let csv100: string;

  test.beforeAll(() => {
    csv5 = writeTempCsv(5);
    csv100 = writeTempCsv(100);
  });

  test.afterAll(() => {
    cleanupFile(csv5);
    cleanupFile(csv100);
  });

  for (const scheme of SCHEMES) {
    test(`default mode 5 rows [${scheme}]`, async ({ page, request }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const session = `ss-default-${scheme}-${Date.now()}`;
      await loadDefault(request, session, csv5);
      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(screenshotsDir, `server-default-5rows--${scheme}.png`),
        fullPage: true,
      });
    });

    test(`buckaroo mode 5 rows [${scheme}]`, async ({ page, request }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const session = `ss-buck-${scheme}-${Date.now()}`;
      await loadBuckaroo(request, session, csv5);
      await page.goto(`${BASE}/s/${session}`);
      // Wait for the full buckaroo widget (data grid + summary stats)
      await page.locator('.df-viewer .ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
      await page.waitForTimeout(1000);
      await page.screenshot({
        path: path.join(screenshotsDir, `server-buckaroo-5rows--${scheme}.png`),
        fullPage: true,
      });
    });

    test(`large dataset 100 rows [${scheme}]`, async ({ page, request }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const session = `ss-large-${scheme}-${Date.now()}`;
      await loadDefault(request, session, csv100);
      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(screenshotsDir, `server-large-100rows--${scheme}.png`),
        fullPage: true,
      });
    });

    test(`buckaroo mode lowcode UI [${scheme}]`, async ({ page, request }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const session = `ss-lowcode-${scheme}-${Date.now()}`;
      await loadBuckaroo(request, session, csv5);
      await page.goto(`${BASE}/s/${session}`);
      // Wait for the buckaroo widget with operations panel
      await page.locator('.df-viewer .ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
      // Click on the operations/columns editor to open lowcode UI
      const columnsTab = page.locator('text=Columns');
      if (await columnsTab.isVisible()) {
        await columnsTab.click();
        await page.waitForTimeout(500);
      }
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(screenshotsDir, `server-buckaroo-lowcode--${scheme}.png`),
        fullPage: true,
      });
    });
  }
});
