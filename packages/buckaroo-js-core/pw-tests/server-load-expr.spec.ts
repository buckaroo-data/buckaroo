import { test, expect } from '@playwright/test';
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { waitForGrid, getCellText } from './server-helpers';

// POST /load_expr against a real server and browser. Needs xorq in the
// server's Python (buckaroo[xorq]); the build dir is made with that same Python.

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;
// Playwright runs from packages/buckaroo-js-core; the repo root is two up, as in the config's webServer.cwd.
const ROOT_DIR = '../..';

// 'idx' and 'name' are rewritten to columns 'a' and 'b'. 'alpha' appears 4 times.
const COL = { idx: 'a', name: 'b' };
const BUILD_EXPR_PY = `
import sys, xorq.api as xo
expr = xo.memtable({
    'idx': list(range(10)),
    'name': ['alpha', 'beta', 'gamma', 'alpha', 'delta',
             'epsilon', 'alpha', 'zeta', 'eta', 'alpha'],
}, name='t')
print(xo.build_expr(expr, builds_dir=sys.argv[1]))
`;

function buildExprDir(buildsRoot: string): string {
  const [python, ...pythonArgs] = (process.env.BUCKAROO_SERVER_PYTHON ?? 'uv run python').split(' ');
  const out = execFileSync(python, [...pythonArgs, '-c', BUILD_EXPR_PY, buildsRoot],
    { cwd: ROOT_DIR, encoding: 'utf8' });
  return out.trim().split('\n').pop()!;
}

async function loadExpr(request: any, sessionId: string, buildDir: string) {
  const resp = await request.post(`${BASE}/load_expr`, {
    data: { session: sessionId, build_dir: buildDir, no_browser: true },
  });
  if (!resp.ok()) {
    throw new Error(`/load_expr failed (${resp.status()}): ${await resp.text()}`);
  }
  return resp.json();
}

async function getPinnedRowCount(page: any): Promise<number> {
  return await page.locator('.df-viewer .ag-floating-top-container .ag-row').count();
}

test.describe('POST /load_expr', () => {
  let buildsRoot: string;
  let buildDir: string;

  test.beforeAll(() => {
    buildsRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'buckaroo_load_expr_'));
    buildDir = buildExprDir(buildsRoot);
  });

  test.afterAll(() => {
    fs.rmSync(buildsRoot, { recursive: true, force: true });
  });

  test('returns metadata for the expression', async ({ request }) => {
    const body = await loadExpr(request, `lx-meta-${Date.now()}`, buildDir);
    expect(body.rows).toBe(10);
    expect(body.columns).toHaveLength(2);
  });

  test('a missing build dir is a 404', async ({ request }) => {
    const resp = await request.post(`${BASE}/load_expr`, {
      data: { session: `lx-404-${Date.now()}`, build_dir: path.join(buildsRoot, 'nope') },
    });
    expect(resp.status()).toBe(404);
    expect((await resp.json()).error_code).toBe('build_dir_not_found');
  });

  test('the session page renders the rows and the pinned stats rows', async ({ page, request }) => {
    const session = `lx-render-${Date.now()}`;
    await loadExpr(request, session, buildDir);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    expect(await getCellText(page, COL.idx, 0)).toBe('0');
    expect(await getCellText(page, COL.name, 0)).toBe('alpha');
    expect(await getCellText(page, COL.name, 1)).toBe('beta');
    expect(await getPinnedRowCount(page)).toBeGreaterThanOrEqual(1);
  });

  test('the summary view shows more stats rows than the main view', async ({ page, request }) => {
    const session = `lx-summary-${Date.now()}`;
    await loadExpr(request, session, buildDir);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);
    const mainPinned = await getPinnedRowCount(page);

    await page.locator('.status-bar').locator('select').first().selectOption('summary');
    await expect.poll(() => getPinnedRowCount(page), { timeout: 15_000 }).toBeGreaterThan(mainPinned);
  });

  test('search filters the rows on the backend', async ({ page, request }) => {
    const session = `lx-search-${Date.now()}`;
    await loadExpr(request, session, buildDir);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    const searchInput = page.locator('.FakeSearchEditor input[type="text"]');
    await searchInput.fill('alpha');
    await searchInput.press('Enter');

    // 'beta' is row 1 unfiltered; after the search row 1 is the second 'alpha'.
    await expect.poll(() => getCellText(page, COL.idx, 1), { timeout: 15_000 }).toBe('3');
    expect(await getCellText(page, COL.name, 1)).toBe('alpha');
  });
});
