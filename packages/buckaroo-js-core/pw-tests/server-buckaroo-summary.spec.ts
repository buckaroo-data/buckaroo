import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

async function loadBuckarooSession(
  request: any,
  sessionId: string,
  filePath: string,
) {
  const resp = await request.post(`${BASE}/load`, {
    data: { session: sessionId, path: filePath, mode: 'buckaroo' },
  });
  if (!resp.ok()) {
    throw new Error(`/load failed (${resp.status()}): ${await resp.text()}`);
  }
  return resp.json();
}

async function waitForDataGrid(page: any, timeout = 15_000) {
  await page.locator('.df-viewer .ag-cell').first().waitFor({ state: 'visible', timeout });
}

async function getPinnedRowCount(page: any): Promise<number> {
  const rows = page.locator('.df-viewer .ag-floating-top-container .ag-row');
  return await rows.count();
}

function writeTempCsv(): string {
  const rows = [
    'name,age,score',
    'Alice,30,88.5',
    'Bob,25,92.3',
    'Charlie,35,76.1',
    'Diana,28,95.0',
    'Eve,32,81.7',
  ];
  const tmpPath = path.join(os.tmpdir(), `buckaroo_summary_${Date.now()}.csv`);
  fs.writeFileSync(tmpPath, rows.join('\n') + '\n');
  return tmpPath;
}

function cleanupFile(p: string) {
  if (p && fs.existsSync(p)) fs.unlinkSync(p);
}

test.describe('Buckaroo mode: summary stats view', () => {
  let csvPath: string;

  test.beforeAll(() => {
    csvPath = writeTempCsv();
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('switching to summary view shows many pinned stats rows', async ({ page, request }) => {
    const session = `summary-${Date.now()}`;
    await loadBuckarooSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForDataGrid(page);

    const mainPinnedCount = await getPinnedRowCount(page);
    expect(mainPinnedCount).toBeGreaterThanOrEqual(1);

    // Switch to summary
    const statusBar = page.locator('.status-bar');
    const dfDisplaySelect = statusBar.locator('select').first();
    await dfDisplaySelect.selectOption('summary');

    // Wait for re-render — the view change triggers a server roundtrip
    await page.waitForTimeout(3000);

    const summaryPinnedCount = await getPinnedRowCount(page);

    // Summary view should have significantly more pinned rows (15) than main (2)
    expect(summaryPinnedCount).toBeGreaterThan(mainPinnedCount);
    expect(summaryPinnedCount).toBeGreaterThanOrEqual(5);
  });

  test('switching to summary and back to main preserves data', async ({ page, request }) => {
    const session = `summary-rt-${Date.now()}`;
    await loadBuckarooSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForDataGrid(page);

    // Switch to summary
    const statusBar = page.locator('.status-bar');
    const dfDisplaySelect = statusBar.locator('select').first();
    await dfDisplaySelect.selectOption('summary');
    await page.waitForTimeout(3000);

    // Switch back to main
    await dfDisplaySelect.selectOption('main');
    await page.waitForTimeout(3000);
    await waitForDataGrid(page);

    // After switching back, verify grid has data cells
    const mainPinnedCount = await getPinnedRowCount(page);
    expect(mainPinnedCount).toBeGreaterThanOrEqual(1);

    const bodyCells = page.locator('.df-viewer .ag-body-viewport .ag-cell');
    await expect(bodyCells.first()).toBeVisible({ timeout: 5000 });
  });
});
