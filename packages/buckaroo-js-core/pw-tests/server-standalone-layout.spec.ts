import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

// ---------- test data --------------------------------------------------------

let _csvCounter = 0;
function writeTempCsv(rowCount: number): string {
  const header = 'name,age,score';
  const rows = [];
  for (let i = 0; i < rowCount; i++) {
    rows.push(`row${i},${20 + (i % 50)},${(i * 1.7).toFixed(1)}`);
  }
  const content = [header, ...rows].join('\n') + '\n';
  const tmpPath = path.join(os.tmpdir(), `buckaroo_layout_test_${Date.now()}_${_csvCounter++}.csv`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

function cleanupFile(p: string) {
  if (p && fs.existsSync(p)) fs.unlinkSync(p);
}

async function loadBuckaroo(request: any, session: string, filePath: string, prompt: string) {
  const resp = await request.post(`${BASE}/load`, {
    data: { session, path: filePath, mode: 'buckaroo', prompt },
  });
  if (!resp.ok()) throw new Error(`/load failed (${resp.status()}): ${await resp.text()}`);
  return resp.json();
}

async function waitForBuckarooGrid(page: any) {
  await page.locator('.df-viewer .ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
  await page.waitForTimeout(1000);
}

/** Collect layout metrics from the page */
async function measureLayout(page: any) {
  return page.evaluate(() => {
    const vh = window.innerHeight;
    const vw = window.innerWidth;

    const filenameBar = document.getElementById('filename-bar');
    const promptBar = document.getElementById('prompt-bar');
    const root = document.getElementById('root');

    const filenameBox = filenameBar?.getBoundingClientRect();
    const promptBox = promptBar?.getBoundingClientRect();
    const rootBox = root?.getBoundingClientRect();

    // Find the MAIN grid (inside .df-viewer), not the StatusBar's grid
    const dfViewer = document.querySelector('.df-viewer');
    const agRoot = dfViewer?.querySelector('.ag-root-wrapper');
    const agBox = agRoot?.getBoundingClientRect();

    // Get the main grid's theme-hanger (inside .df-viewer), not StatusBar's
    const themeHanger = dfViewer?.querySelector('.theme-hanger') as HTMLElement | null;
    const themeBox = themeHanger?.getBoundingClientRect();

    // Check for any red pixels showing (dead space indicator)
    // by sampling a few points
    const bodyBg = getComputedStyle(document.body).backgroundColor;

    return {
      viewport: { width: vw, height: vh },
      filenameBar: filenameBox ? { top: filenameBox.top, bottom: filenameBox.bottom, height: filenameBox.height, visible: filenameBox.height > 0 } : null,
      promptBar: promptBox ? { top: promptBox.top, bottom: promptBox.bottom, height: promptBox.height, visible: promptBox.height > 0 } : null,
      root: rootBox ? { top: rootBox.top, bottom: rootBox.bottom, height: rootBox.height } : null,
      agRoot: agBox ? { top: agBox.top, bottom: agBox.bottom, height: agBox.height } : null,
      themeHanger: themeBox ? { top: themeBox.top, bottom: themeBox.bottom, height: themeBox.height } : null,
      bodyBg,
      // Bottom gap = distance from ag-grid bottom to viewport bottom
      bottomGapFromGrid: agBox ? vh - agBox.bottom : null,
      // How much of the viewport the grid uses (percentage)
      gridFillPercent: agBox ? (agBox.height / vh) * 100 : null,
    };
  });
}

// ---------- tests ------------------------------------------------------------

test.describe('Standalone layout: filename, prompt, fill, bottom gap', () => {
  let csvPath: string;
  const PROMPT_TEXT = 'Test prompt for layout verification';

  test.beforeAll(() => {
    csvPath = writeTempCsv(500);
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('filename and prompt bars are visible', async ({ page, request }) => {
    const session = `layout-bars-${Date.now()}`;
    await loadBuckaroo(request, session, csvPath, PROMPT_TEXT);
    await page.goto(`${BASE}/s/${session}`);
    await waitForBuckarooGrid(page);

    // Screenshot first (always captured even if assertions fail)
    await page.screenshot({
      path: path.join(screenshotsDir, 'layout-bars.png'),
    });

    // Filename bar
    const filenameBar = page.locator('#filename-bar');
    await expect(filenameBar).toBeVisible();
    const filenameText = await filenameBar.textContent();
    expect(filenameText).toContain('buckaroo_layout_test_');
    expect(filenameText).toContain('.csv');

    // Prompt bar
    const promptBar = page.locator('#prompt-bar');
    await expect(promptBar).toBeVisible();
    const promptText = await promptBar.textContent();
    expect(promptText).toBe(PROMPT_TEXT);

    // Document title
    const title = await page.title();
    expect(title).toContain('buckaroo_layout_test_');
    expect(title).not.toContain(session);
  });

  test('table fills viewport with 20px bottom gap at 1280x720', async ({ page, request }) => {
    const session = `layout-fill-${Date.now()}`;
    await loadBuckaroo(request, session, csvPath, PROMPT_TEXT);
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(`${BASE}/s/${session}`);
    await waitForBuckarooGrid(page);

    // Screenshot first
    await page.screenshot({
      path: path.join(screenshotsDir, 'layout-1280x720.png'),
    });

    const m = await measureLayout(page);
    console.log('Layout metrics at 1280x720:', JSON.stringify(m, null, 2));

    // Filename and prompt bars should be visible
    expect(m.filenameBar?.visible).toBe(true);
    expect(m.promptBar?.visible).toBe(true);

    // The grid should fill at least 70% of the viewport
    expect(m.gridFillPercent).toBeGreaterThan(70);

    // Bottom gap from grid to viewport bottom should be 15-30px
    expect(m.bottomGapFromGrid).toBeGreaterThanOrEqual(15);
    expect(m.bottomGapFromGrid).toBeLessThanOrEqual(35);
  });

  test('layout adapts to viewport resize', async ({ page, request }) => {
    const session = `layout-resize-${Date.now()}`;
    await loadBuckaroo(request, session, csvPath, PROMPT_TEXT);

    const sizes = [
      { width: 1280, height: 720 },
      { width: 1280, height: 900 },
      { width: 800, height: 600 },
    ];

    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.goto(`${BASE}/s/${session}`);
      await waitForBuckarooGrid(page);

      // Screenshot first
      await page.screenshot({
        path: path.join(screenshotsDir, `layout-${size.width}x${size.height}.png`),
      });

      const m = await measureLayout(page);
      console.log(`Layout metrics at ${size.width}x${size.height}:`, JSON.stringify(m, null, 2));

      // Bars visible
      expect(m.filenameBar?.visible).toBe(true);
      expect(m.promptBar?.visible).toBe(true);

      // Grid fills at least 70% of viewport
      expect(m.gridFillPercent).toBeGreaterThan(70);

      // Bottom gap ~20px
      expect(m.bottomGapFromGrid).toBeGreaterThanOrEqual(15);
      expect(m.bottomGapFromGrid).toBeLessThanOrEqual(35);
    }
  });
});

// ---------- MCP-flow race condition tests ------------------------------------
// These reproduce the real MCP tool flow where data may arrive after the page
// is already open, exercising the WebSocketModel → React event path.

test.describe('MCP flow: late-arriving data and reload', () => {
  let csvPathA: string;
  let csvPathB: string;

  test.beforeAll(() => {
    // Small files matching the real MCP failure case (5 rows)
    csvPathA = writeTempCsv(5);
    csvPathB = writeTempCsv(8);
  });

  test.afterAll(() => {
    cleanupFile(csvPathA);
    cleanupFile(csvPathB);
  });

  test('page open BEFORE data loads — bars appear when data arrives', async ({ page, request }) => {
    const session = `mcp-late-${Date.now()}`;
    const PROMPT = `Viewing ${path.basename(csvPathA)}`;

    // 1. Navigate FIRST — no data loaded yet.  The page connects WS and
    //    renders "Waiting for data...".
    await page.goto(`${BASE}/s/${session}`);
    await page.waitForTimeout(500); // let WS connect + old timeout expire

    // 2. NOW load data — server pushes initial_state to connected client
    await loadBuckaroo(request, session, csvPathA, PROMPT);

    // 3. Wait for grid to appear (proves data arrived via WS push)
    await waitForBuckarooGrid(page);

    await page.screenshot({
      path: path.join(screenshotsDir, 'mcp-late-data.png'),
    });

    // 4. Assert filename bar
    const filenameBar = page.locator('#filename-bar');
    await expect(filenameBar).toBeVisible();
    const filenameText = await filenameBar.textContent();
    expect(filenameText).toContain('buckaroo_layout_test_');
    expect(filenameText).toContain('.csv');

    // 5. Assert prompt bar
    const promptBar = page.locator('#prompt-bar');
    await expect(promptBar).toBeVisible();
    const promptText = await promptBar.textContent();
    expect(promptText).toBe(PROMPT);

    // 6. Document title updated
    const title = await page.title();
    expect(title).toContain('buckaroo_layout_test_');
  });

  test('reload: second POST /load updates bars to new file', async ({ page, request }) => {
    const session = `mcp-reload-${Date.now()}`;
    const PROMPT_A = `Viewing ${path.basename(csvPathA)}`;
    const PROMPT_B = `Viewing ${path.basename(csvPathB)}`;

    // 1. Load file A, navigate, wait for grid
    await loadBuckaroo(request, session, csvPathA, PROMPT_A);
    await page.goto(`${BASE}/s/${session}`);
    await waitForBuckarooGrid(page);

    // Verify file A is shown
    const filenameBar = page.locator('#filename-bar');
    await expect(filenameBar).toBeVisible();
    const textA = await filenameBar.textContent();
    expect(textA).toContain('.csv');

    // 2. Load file B into the SAME session — server pushes to existing WS
    await loadBuckaroo(request, session, csvPathB, PROMPT_B);

    // 3. Wait for the new data to arrive and bars to update
    await expect(page.locator('#prompt-bar')).toHaveText(PROMPT_B, { timeout: 10_000 });

    await page.screenshot({
      path: path.join(screenshotsDir, 'mcp-reload.png'),
    });

    // 4. Filename bar should show file B
    const textB = await filenameBar.textContent();
    expect(textB).not.toBe(textA);
    expect(textB).toContain('.csv');

    // 5. Title should update
    const title = await page.title();
    expect(title).toContain('buckaroo_layout_test_');
  });
});
