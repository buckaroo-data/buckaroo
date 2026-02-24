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

function writeTempCsv(): string {
  const rows = [
    'name,age,score',
    'Alice,30,88.5',
    'Bob,25,92.3',
    'Charlie,35,76.1',
    'Diana,28,95.0',
    'Eve,32,81.7',
  ];
  const tmpPath = path.join(os.tmpdir(), `buckaroo_search_${Date.now()}.csv`);
  fs.writeFileSync(tmpPath, rows.join('\n') + '\n');
  return tmpPath;
}

function cleanupFile(p: string) {
  if (p && fs.existsSync(p)) fs.unlinkSync(p);
}

test.describe('Buckaroo mode: search filtering', () => {
  let csvPath: string;

  test.beforeAll(() => {
    csvPath = writeTempCsv();
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('searching filters the table data, not just the status bar count', async ({ page, request }) => {
    const session = `search-${Date.now()}`;
    await loadBuckarooSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForDataGrid(page);

    // Get the initial data grid body text — should contain all names
    const dataGrid = page.locator('.df-viewer');
    const initialBodyText = await dataGrid.textContent();
    expect(initialBodyText).toContain('Alice');
    expect(initialBodyText).toContain('Bob');

    // Type "Alice" in the search input and press Enter
    const searchInput = page.locator('.FakeSearchEditor input[type="text"]');
    await searchInput.fill('Alice');
    await searchInput.press('Enter');

    // Wait for server roundtrip
    await page.waitForTimeout(3000);

    // The table data should update to show only matching rows.
    // With the bug, the data grid still shows all 5 rows because the
    // datasource/cache key doesn't change when quick_command_args changes.
    const filteredBodyText = await dataGrid.textContent();
    expect(filteredBodyText).toContain('Alice');
    expect(filteredBodyText).not.toContain('Bob');
    expect(filteredBodyText).not.toContain('Charlie');
  });
});
