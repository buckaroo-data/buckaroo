import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

/**
 * Load a session in buckaroo mode (full analysis pipeline with summary stats).
 */
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

/**
 * Wait for the main data grid (not the status bar) to have rendered cells.
 * The data grid lives inside .df-viewer; the status bar has its own AG Grid.
 */
async function waitForDataGrid(page: any, timeout = 15_000) {
  await page.locator('.df-viewer .ag-cell').first().waitFor({ state: 'visible', timeout });
}

/**
 * Count pinned (top) rows in the main data grid.
 */
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

    // Main view: pinned rows = [dtype, histogram] → 2 pinned rows
    const mainPinnedCount = await getPinnedRowCount(page);
    expect(mainPinnedCount).toBeGreaterThanOrEqual(1);

    // Find the df_display dropdown in the status bar and switch to "summary"
    const statusBar = page.locator('.status-bar');
    const dfDisplaySelect = statusBar.locator('select').first();
    await dfDisplaySelect.selectOption('summary');

    // Wait for re-render
    await page.waitForTimeout(3000);

    // Summary view should have many more pinned rows (dtype, non_null_count,
    // null_count, unique_count, distinct_count, mean, std, min, median, max,
    // most_freq, 2nd_freq, 3rd_freq, 4th_freq, 5th_freq = up to 15).
    // With the bug, the grid stays in infinite mode and doesn't properly
    // update its pinned rows — we'd see the same 2 from main view or fewer.
    const summaryPinnedCount = await getPinnedRowCount(page);

    // The summary view should have significantly more pinned rows than main
    // Main has ~2 (dtype + histogram), summary has ~15
    expect(summaryPinnedCount).toBeGreaterThan(mainPinnedCount);
    expect(summaryPinnedCount).toBeGreaterThanOrEqual(5);
  });

  test('switching to summary and back to main preserves data', async ({ page, request }) => {
    const session = `summary-rt-${Date.now()}`;
    await loadBuckarooSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForDataGrid(page);

    // Switch to summary view
    const statusBar = page.locator('.status-bar');
    const dfDisplaySelect = statusBar.locator('select').first();
    await dfDisplaySelect.selectOption('summary');
    await page.waitForTimeout(3000);

    // Switch back to main
    await dfDisplaySelect.selectOption('main');
    await page.waitForTimeout(3000);

    // Wait for data grid cells to reappear
    await waitForDataGrid(page);

    // After switching back, the main view should render its pinned rows
    // (dtype + histogram), proving the grid properly remounted
    const mainPinnedCount = await getPinnedRowCount(page);
    expect(mainPinnedCount).toBeGreaterThanOrEqual(1);

    // Also verify data cells are present (not just pinned rows)
    const bodyCells = page.locator('.df-viewer .ag-body-viewport .ag-cell');
    await expect(bodyCells.first()).toBeVisible({ timeout: 5000 });
  });
});
