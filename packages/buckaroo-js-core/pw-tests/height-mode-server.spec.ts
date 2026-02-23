import { test, expect } from '@playwright/test';
import { waitForGrid } from './server-helpers';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots', 'height-mode');

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

// --- Test data ---

function writeTempCsv(rowCount: number): string {
  const header = 'name,age,score';
  const rows = [];
  for (let i = 0; i < rowCount; i++) {
    rows.push(`row${i},${20 + (i % 50)},${(i * 1.7).toFixed(1)}`);
  }
  const content = [header, ...rows].join('\n') + '\n';
  const tmpPath = path.join(os.tmpdir(), `buckaroo_height_test_${Date.now()}_${rowCount}.csv`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

function cleanupFile(p: string) {
  if (p && fs.existsSync(p)) fs.unlinkSync(p);
}

async function loadViewer(request: any, session: string, filePath: string) {
  const resp = await request.post(`${BASE}/load`, {
    data: { session, path: filePath },
  });
  if (!resp.ok()) throw new Error(`/load failed (${resp.status()}): ${await resp.text()}`);
  return resp.json();
}

// --- Tests ---

test.describe('Height mode server integration', () => {
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

  test('fill mode: 100-row table fills viewport with no black gap', async ({ page, request }) => {
    const session = `height-fill-100-${Date.now()}`;
    await loadViewer(request, session, csv100);
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);
    await page.waitForTimeout(1000);

    // Measure the gap between the bottom of .theme-hanger and the viewport bottom
    const gap = await page.evaluate(() => {
      const el = document.querySelector('.theme-hanger');
      if (!el) return 9999;
      const rect = el.getBoundingClientRect();
      return window.innerHeight - rect.bottom;
    });

    // In fill mode, the grid should extend close to the bottom of the viewport.
    // Allow some tolerance for borders/margins.
    // NOTE: This test will fail before implementation (gap will be ~half the screen).
    expect(gap).toBeLessThan(50);

    await page.screenshot({
      path: path.join(screenshotsDir, 'server-fill-100rows.png'),
      fullPage: true,
    });
  });

  test('fill mode: 5-row short table does not stretch', async ({ page, request }) => {
    const session = `height-fill-5-${Date.now()}`;
    await loadViewer(request, session, csv5);
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);
    await page.waitForTimeout(1000);

    // Short table: the grid should be small, not filling the viewport
    const gridHeight = await page.evaluate(() => {
      const el = document.querySelector('.theme-hanger');
      if (!el) return 0;
      return el.getBoundingClientRect().height;
    });

    // 5 rows + header + pinned ≈ under 250px
    expect(gridHeight).toBeLessThan(250);

    await page.screenshot({
      path: path.join(screenshotsDir, 'server-fill-5rows-short.png'),
      fullPage: true,
    });
  });

  test('fill mode: resize window causes grid to resize', async ({ page, request }) => {
    const session = `height-fill-resize-${Date.now()}`;
    await loadViewer(request, session, csv100);

    // Start with a large viewport
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);
    await page.waitForTimeout(1000);

    const heightBefore = await page.evaluate(() => {
      const el = document.querySelector('.theme-hanger');
      return el ? el.getBoundingClientRect().height : 0;
    });

    await page.screenshot({
      path: path.join(screenshotsDir, 'server-fill-resize-before.png'),
      fullPage: true,
    });

    // Resize to a smaller viewport
    await page.setViewportSize({ width: 1024, height: 400 });
    await page.waitForTimeout(1000);

    const heightAfter = await page.evaluate(() => {
      const el = document.querySelector('.theme-hanger');
      return el ? el.getBoundingClientRect().height : 0;
    });

    await page.screenshot({
      path: path.join(screenshotsDir, 'server-fill-resize-after.png'),
      fullPage: true,
    });

    // The grid should have gotten smaller after resize
    // NOTE: This test will fail before implementation (height is fixed pixels).
    expect(heightAfter).toBeLessThan(heightBefore);
    // The difference should be significant (not just 1-2px jitter)
    expect(heightBefore - heightAfter).toBeGreaterThan(100);
  });

  // Screenshots for comparison viewer (both viewport sizes)
  for (const scheme of ['light', 'dark'] as const) {
    test(`server screenshot 100 rows [${scheme}]`, async ({ page, request }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const session = `height-ss-100-${scheme}-${Date.now()}`;
      await loadViewer(request, session, csv100);
      await page.setViewportSize({ width: 1024, height: 768 });
      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(screenshotsDir, `server-100rows--${scheme}.png`),
        fullPage: true,
      });
    });

    test(`server screenshot 5 rows [${scheme}]`, async ({ page, request }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const session = `height-ss-5-${scheme}-${Date.now()}`;
      await loadViewer(request, session, csv5);
      await page.setViewportSize({ width: 1024, height: 768 });
      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(screenshotsDir, `server-5rows--${scheme}.png`),
        fullPage: true,
      });
    });
  }
});
