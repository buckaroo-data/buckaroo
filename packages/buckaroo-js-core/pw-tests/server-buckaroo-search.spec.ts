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

  test('diagnostic: buckaroo mode renders grid', async ({ page, request }) => {
    const consoleLogs: string[] = [];
    page.on('console', (msg: any) => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));
    page.on('pageerror', (err: any) => consoleLogs.push(`[PAGE_ERROR] ${err.message}`));

    const session = `diag-${Date.now()}`;
    await loadBuckarooSession(request, session, csvPath);

    // Check diagnostics endpoint
    const diagResp = await request.get(`${BASE}/diagnostics`);
    const diag = await diagResp.json();
    console.log('DIAG:static_path:', diag.static_path);
    console.log('DIAG:static_files:', JSON.stringify(diag.static_files));
    console.log('DIAG:python_executable:', diag.python_executable);
    console.log('DIAG:dependencies:', JSON.stringify(diag.dependencies));

    // Connect WebSocket directly to capture initial_state
    const wsUrl = `ws://localhost:${PORT}/ws/${session}`;
    const initialState: any = await page.evaluate(async (url: string) => {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(url);
        ws.binaryType = 'arraybuffer';
        const timeout = setTimeout(() => { ws.close(); reject(new Error('WS timeout')); }, 5000);
        ws.onmessage = (event: MessageEvent) => {
          if (typeof event.data === 'string') {
            const msg = JSON.parse(event.data);
            if (msg.type === 'initial_state') {
              clearTimeout(timeout);
              ws.close();
              // Extract key fields (avoid logging huge data)
              resolve({
                mode: msg.mode,
                df_meta: msg.df_meta,
                df_display_args_keys: Object.keys(msg.df_display_args || {}),
                df_display_args_main_data_key: msg.df_display_args?.main?.data_key,
                df_display_args_main_summary_key: msg.df_display_args?.main?.summary_stats_key,
                df_display_args_main_has_column_config: !!(msg.df_display_args?.main?.df_viewer_config?.column_config?.length),
                df_data_dict_keys: Object.keys(msg.df_data_dict || {}),
                df_data_dict_main_length: msg.df_data_dict?.main?.length,
                df_data_dict_all_stats_type: typeof msg.df_data_dict?.all_stats === 'object' ? (msg.df_data_dict?.all_stats?.format || 'array') : typeof msg.df_data_dict?.all_stats,
                has_buckaroo_state: !!msg.buckaroo_state,
                buckaroo_state_df_display: msg.buckaroo_state?.df_display,
              });
            }
          }
        };
        ws.onerror = () => { clearTimeout(timeout); reject(new Error('WS error')); };
      });
    }, wsUrl);
    console.log('DIAG:initial_state:', JSON.stringify(initialState));

    await page.goto(`${BASE}/s/${session}`);

    // Wait up to 10s, logging state every 2s
    for (let i = 0; i < 5; i++) {
      await page.waitForTimeout(2000);
      const rootText = await page.locator('#root').textContent();
      const agCellCount = await page.locator('.ag-cell').count();
      const dfViewerCount = await page.locator('.df-viewer').count();
      const agOverlayCount = await page.locator('.ag-overlay').count();
      console.log(`DIAG:t=${(i+1)*2}s root_text_start="${rootText?.substring(0, 100)}" ag-cells=${agCellCount} df-viewers=${dfViewerCount} ag-overlays=${agOverlayCount}`);
      if (agCellCount > 0) break;
    }

    // Log console messages from browser
    for (const log of consoleLogs) {
      console.log('DIAG:browser:', log);
    }

    // The grid should eventually render
    const cellCount = await page.locator('.df-viewer .ag-cell').count();
    expect(cellCount).toBeGreaterThan(0);
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
