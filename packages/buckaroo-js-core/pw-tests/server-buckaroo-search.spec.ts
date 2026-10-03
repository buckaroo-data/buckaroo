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

  test('live typing sends search_string, not quick_command_args.search (#998)', async ({ page, request }) => {
    // Server mode runs search on the per-client row-only path: the term
    // goes out as buckaroo_state.search_string, the dataflow fields stay as
    // they are, the server answers with one overlay initial_state plus the
    // filtered rows, and the status bar's filtered count follows the rows.
    const session = `search-rows-${Date.now()}`;
    await loadBuckarooSession(request, session, csvPath);

    const sent: any[] = [];
    const received: any[] = [];
    page.on('websocket', (ws) => {
      ws.on('framesent', (f) => { if (typeof f.payload === 'string') sent.push(JSON.parse(f.payload)); });
      ws.on('framereceived', (f) => {
        if (typeof f.payload !== 'string') return;
        try { received.push(JSON.parse(f.payload)); } catch { /* binary-ish text frame */ }
      });
    });

    await page.goto(`${BASE}/s/${session}`);
    await waitForDataGrid(page);
    const sentBefore = sent.length;
    const receivedBefore = received.length;

    // No Enter: the 300 ms debounce fires after the last key.
    const searchInput = page.locator('.FakeSearchEditor input[type="text"]');
    await searchInput.click();
    await searchInput.pressSequentially('Alice', { delay: 50 });
    await page.waitForTimeout(3000);

    const stateChanges = sent.slice(sentBefore).filter((m) => m.type === 'buckaroo_state_change');
    expect(stateChanges.length).toBe(1);
    expect(stateChanges[0].new_state.search_string).toBe('Alice');
    expect(stateChanges[0].new_state.quick_command_args).toEqual({});

    const initialStates = received.slice(receivedBefore).filter((m) => m.type === 'initial_state');
    expect(initialStates.length).toBe(1);
    expect(initialStates[0].buckaroo_state.search_string).toBe('Alice');

    const rowResps = received.slice(receivedBefore).filter((m) => m.type === 'infinite_resp');
    expect(rowResps.length).toBeGreaterThan(0);
    expect(rowResps[rowResps.length - 1].length).toBe(1);

    const bodyText = await page.locator('.df-viewer').textContent();
    expect(bodyText).toContain('Alice');
    expect(bodyText).not.toContain('Bob');
    await expect(page.locator('.status-bar [col-id="filtered_rows"]').last()).toHaveText('1');
    await expect(searchInput).toHaveValue('Alice');
  });
});
