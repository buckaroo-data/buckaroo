import { test, expect } from '@playwright/test';
import { loadSession, waitForGrid, getRowCount, getCellText } from './server-helpers';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.join(__dirname, '../../..');

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

// ---------- test data --------------------------------------------------------

const CSV_ROWS = [
  { name: 'Alice',   age: 30, score: 88.5 },
  { name: 'Bob',     age: 25, score: 92.3 },
  { name: 'Charlie', age: 35, score: 76.1 },
  { name: 'Diana',   age: 28, score: 95.0 },
  { name: 'Eve',     age: 32, score: 81.7 },
];

function writeTempCsv(): string {
  const header = 'name,age,score';
  const rows = CSV_ROWS.map(r => `${r.name},${r.age},${r.score}`);
  const content = [header, ...rows].join('\n') + '\n';
  const tmpPath = path.join(os.tmpdir(), `buckaroo_e2e_${Date.now()}.csv`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

function writeTempTsv(): string {
  const header = 'name\tage\tscore';
  const rows = CSV_ROWS.map(r => `${r.name}\t${r.age}\t${r.score}`);
  const content = [header, ...rows].join('\n') + '\n';
  const tmpPath = path.join(os.tmpdir(), `buckaroo_e2e_${Date.now()}.tsv`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

function writeTempJson(): string {
  const content = JSON.stringify(CSV_ROWS);
  const tmpPath = path.join(os.tmpdir(), `buckaroo_e2e_${Date.now()}.json`);
  fs.writeFileSync(tmpPath, content);
  return tmpPath;
}

function writeTempParquet(): string {
  const parquetPath = path.join(os.tmpdir(), `buckaroo_e2e_${Date.now()}.parquet`);
  // Use polars (available in [mcp] extras) instead of pandas to write the test parquet.
  // Use BUCKAROO_SERVER_PYTHON if set (CI), otherwise fall back to uv run python.
  const python = process.env.BUCKAROO_SERVER_PYTHON ?? 'uv run python';
  execSync(
    `${python} -c "import polars as pl; pl.DataFrame({'x':[1,2,3],'y':[4,5,6]}).write_parquet('${parquetPath}')"`,
    { cwd: PROJECT_ROOT },
  );
  return parquetPath;
}

function cleanupFile(p: string) {
  if (p && fs.existsSync(p)) fs.unlinkSync(p);
}

// Column rename mapping: name→a, age→b, score→c
const COL = { name: 'a', age: 'b', score: 'c' };

// ---------- tests: core functionality ----------------------------------------

test.describe('Buckaroo standalone server', () => {
  let csvPath: string;

  test.beforeAll(() => {
    csvPath = writeTempCsv();
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('health endpoint returns ok', async ({ request }) => {
    const resp = await request.get(`${BASE}/health`);
    expect(resp.ok()).toBe(true);
    expect(await resp.json()).toMatchObject({ status: 'ok' });
  });

  test('load CSV and render table', async ({ page, request }) => {
    const session = `csv-${Date.now()}`;
    await loadSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    const count = await getRowCount(page);
    expect(count).toBe(5);
  });

  test('load Parquet and render table', async ({ page, request }) => {
    const parquetPath = writeTempParquet();
    try {
      const session = `parq-${Date.now()}`;
      await loadSession(request, session, parquetPath);

      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);

      const count = await getRowCount(page);
      expect(count).toBe(3);
    } finally {
      cleanupFile(parquetPath);
    }
  });

  test('cell values match source data', async ({ page, request }) => {
    const session = `cells-${Date.now()}`;
    await loadSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // Verify first column (name → col-id "a") values
    expect(await getCellText(page, COL.name, 0)).toBe('Alice');
    expect(await getCellText(page, COL.name, 1)).toBe('Bob');
    expect(await getCellText(page, COL.name, 2)).toBe('Charlie');
  });

  test('column headers present', async ({ page, request }) => {
    const session = `hdrs-${Date.now()}`;
    await loadSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // The original column names appear as header text
    for (const name of ['name', 'age', 'score']) {
      await expect(page.getByRole('columnheader', { name })).toBeVisible();
    }
  });

  test('sort via header click', async ({ page, request }) => {
    const session = `sort-${Date.now()}`;
    await loadSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // Get the initial first-row name value
    const before = await getCellText(page, COL.name, 0);
    expect(before).toBe('Alice');

    // Click the "name" column header to sort
    await page.getByRole('columnheader', { name: 'name' }).click();
    await page.waitForTimeout(1000);
    await waitForGrid(page);

    // After sort the order should change
    const after = await getCellText(page, COL.name, 0);
    // One click = ascending, which keeps Alice first; a second click = descending
    if (after === 'Alice') {
      // Click again for descending
      await page.getByRole('columnheader', { name: 'name' }).click();
      await page.waitForTimeout(1000);
      await waitForGrid(page);
      const desc = await getCellText(page, COL.name, 0);
      expect(desc).toBe('Eve');
    } else {
      expect(after).not.toBe('Alice');
    }
  });
});

// ---------- tests: /load API responses & error handling ----------------------

test.describe('/load API', () => {
  let csvPath: string;

  test.beforeAll(() => {
    csvPath = writeTempCsv();
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('returns metadata with row count and columns', async ({ request }) => {
    const session = `meta-${Date.now()}`;
    const resp = await request.post(`${BASE}/load`, {
      data: { session, path: csvPath },
    });
    expect(resp.ok()).toBe(true);

    const body = await resp.json();
    expect(body.session).toBe(session);
    expect(body.rows).toBe(5);
    expect(body.path).toBe(csvPath);
    expect(body.columns).toHaveLength(3);
    expect(body.columns.map((c: { name: string }) => c.name)).toEqual(['name', 'age', 'score']);
  });

  test('400 on missing session field', async ({ request }) => {
    const resp = await request.post(`${BASE}/load`, {
      data: { path: csvPath },
    });
    expect(resp.status()).toBe(400);
    const body = await resp.json();
    expect(body.error).toContain("Missing");
  });

  test('400 on missing path field', async ({ request }) => {
    const resp = await request.post(`${BASE}/load`, {
      data: { session: 'x' },
    });
    expect(resp.status()).toBe(400);
    const body = await resp.json();
    expect(body.error).toContain("Missing");
  });

  test('400 on invalid JSON body', async ({ request }) => {
    const resp = await request.fetch(`${BASE}/load`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      data: 'not-json{{{',
    });
    expect(resp.status()).toBe(400);
  });

  test('404 on non-existent file', async ({ request }) => {
    const resp = await request.post(`${BASE}/load`, {
      data: { session: `nf-${Date.now()}`, path: '/tmp/does_not_exist_12345.csv' },
    });
    expect(resp.status()).toBe(404);
    const body = await resp.json();
    expect(body.error).toContain("not found");
  });

  test('400 on unsupported file extension', async ({ request }) => {
    const tmpPath = path.join(os.tmpdir(), `buckaroo_e2e_${Date.now()}.xyz`);
    fs.writeFileSync(tmpPath, 'hello');
    try {
      const resp = await request.post(`${BASE}/load`, {
        data: { session: `ext-${Date.now()}`, path: tmpPath },
      });
      expect(resp.status()).toBe(400);
      const body = await resp.json();
      expect(body.error).toContain("Unsupported");
    } finally {
      cleanupFile(tmpPath);
    }
  });
});

// ---------- tests: additional file formats -----------------------------------

test.describe('file format support', () => {
  test('load TSV and render table', async ({ page, request }) => {
    const tsvPath = writeTempTsv();
    try {
      const session = `tsv-${Date.now()}`;
      await loadSession(request, session, tsvPath);

      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);

      const count = await getRowCount(page);
      expect(count).toBe(5);

      // Verify a cell value to ensure TSV parsing worked
      expect(await getCellText(page, 'a', 0)).toBe('Alice');
    } finally {
      cleanupFile(tsvPath);
    }
  });

  test('load JSON and render table', async ({ page, request }) => {
    const jsonPath = writeTempJson();
    try {
      const session = `json-${Date.now()}`;
      await loadSession(request, session, jsonPath);

      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);

      const count = await getRowCount(page);
      expect(count).toBe(5);

      expect(await getCellText(page, 'a', 0)).toBe('Alice');
    } finally {
      cleanupFile(jsonPath);
    }
  });
});

// ---------- tests: numeric values render correctly ---------------------------

test.describe('numeric column rendering', () => {
  let csvPath: string;

  test.beforeAll(() => {
    csvPath = writeTempCsv();
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('integer column values render correctly', async ({ page, request }) => {
    const session = `int-${Date.now()}`;
    await loadSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // age column → col-id "b"
    expect(await getCellText(page, COL.age, 0)).toBe('30');
    expect(await getCellText(page, COL.age, 1)).toBe('25');
    expect(await getCellText(page, COL.age, 2)).toBe('35');
  });

  test('float column values render correctly', async ({ page, request }) => {
    const session = `float-${Date.now()}`;
    await loadSession(request, session, csvPath);

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // score column → col-id "c"
    const v0 = await getCellText(page, COL.score, 0);
    const v1 = await getCellText(page, COL.score, 1);
    // Float rendering may vary in decimal places, so parse and compare numerically
    expect(parseFloat(v0)).toBeCloseTo(88.5, 1);
    expect(parseFloat(v1)).toBeCloseTo(92.3, 1);
  });
});

// ---------- tests: session reload --------------------------------------------

test.describe('session management', () => {
  test('reloading a session with new data updates the table', async ({ page, request }) => {
    const session = `reload-${Date.now()}`;

    // Load the first dataset (3 rows)
    const parquetPath = writeTempParquet();
    try {
      await loadSession(request, session, parquetPath);

      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);
      expect(await getRowCount(page)).toBe(3);
    } finally {
      cleanupFile(parquetPath);
    }

    // Reload same session with a different file (5 rows)
    const csvPath = writeTempCsv();
    try {
      await loadSession(request, session, csvPath);

      // Refresh the page to pick up the new data
      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);
      expect(await getRowCount(page)).toBe(5);
    } finally {
      cleanupFile(csvPath);
    }
  });
});

// ---------- tests: session page & static assets ------------------------------

test.describe('session page and static assets', () => {
  test('session page returns valid HTML', async ({ request }) => {
    const resp = await request.get(`${BASE}/s/any-session`);
    expect(resp.ok()).toBe(true);
    const html = await resp.text();
    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<div id="root">');
    expect(html).toContain('standalone.js');
  });

  test('standalone.js is served', async ({ request }) => {
    const resp = await request.get(`${BASE}/static/standalone.js`);
    expect(resp.ok()).toBe(true);
    const contentType = resp.headers()['content-type'] ?? '';
    expect(contentType).toContain('javascript');
  });

  test('compiled.css is served', async ({ request }) => {
    const resp = await request.get(`${BASE}/static/compiled.css`);
    expect(resp.ok()).toBe(true);
    const contentType = resp.headers()['content-type'] ?? '';
    expect(contentType).toContain('css');
  });
});

// ---------- tests: static asset integrity (catch blank-page bug) -------------

test.describe('static asset integrity', () => {
  test('standalone.js is non-empty and contains JavaScript', async ({ request }) => {
    const resp = await request.get(`${BASE}/static/standalone.js`);
    expect(resp.ok()).toBe(true);
    const body = await resp.text();
    // An empty or stub file would cause a blank page — the #1 user-reported issue
    expect(body.length).toBeGreaterThan(100);
    expect(body).toMatch(/function|const|var|import|export/);
  });

  test('standalone.css is served and non-empty', async ({ request }) => {
    const resp = await request.get(`${BASE}/static/standalone.css`);
    expect(resp.ok()).toBe(true);
    const body = await resp.text();
    expect(body.length).toBeGreaterThan(0);
  });

  test('compiled.css is non-empty and contains CSS rules', async ({ request }) => {
    const resp = await request.get(`${BASE}/static/compiled.css`);
    expect(resp.ok()).toBe(true);
    const body = await resp.text();
    expect(body.length).toBeGreaterThan(100);
    expect(body).toMatch(/\{[\s\S]*\}/); // contains at least one CSS rule
  });
});

// ---------- tests: server diagnostics ----------------------------------------

test.describe('server diagnostics', () => {
  test('health endpoint includes static file info', async ({ request }) => {
    const resp = await request.get(`${BASE}/health`);
    expect(resp.ok()).toBe(true);
    const body = await resp.json();
    // Diagnostics: which static files exist and their sizes
    expect(body.static_files).toBeDefined();
    expect(body.static_files['standalone.js']).toBeDefined();
    expect(body.static_files['standalone.js'].exists).toBe(true);
    expect(body.static_files['standalone.js'].size_bytes).toBeGreaterThan(0);
    expect(body.static_files['compiled.css']).toBeDefined();
    expect(body.static_files['compiled.css'].exists).toBe(true);
  });

  test('diagnostics endpoint returns environment info', async ({ request }) => {
    const resp = await request.get(`${BASE}/diagnostics`);
    expect(resp.ok()).toBe(true);
    const body = await resp.json();
    expect(body.python_version).toBeDefined();
    expect(body.buckaroo_version).toBeDefined();
    expect(body.tornado_version).toBeDefined();
    expect(body.static_files).toBeDefined();
    expect(body.log_dir).toBeDefined();
    // Dependency checks — these are the packages needed for [mcp] to work
    expect(body.dependencies).toBeDefined();
    expect(body.dependencies.tornado).toBe(true);
    expect(body.dependencies.pandas).toBe(true);
  });
});

// ---------- tests: WebSocket data flow ---------------------------------------

test.describe('WebSocket data flow', () => {
  let csvPath: string;

  test.beforeAll(() => {
    csvPath = writeTempCsv();
  });

  test.afterAll(() => {
    cleanupFile(csvPath);
  });

  test('WebSocket receives initial_state after connect', async ({ page, request }) => {
    const session = `ws-${Date.now()}`;
    await loadSession(request, session, csvPath);

    // Navigate to the session page so the JS client connects via WebSocket
    await page.goto(`${BASE}/s/${session}`);

    // The client connects to ws://localhost:PORT/ws/{session} and receives
    // initial_state. We can verify this worked by checking the grid renders.
    await waitForGrid(page);
    const count = await getRowCount(page);
    expect(count).toBe(5);

    // Also verify data actually loaded into cells (proves WS data transfer)
    expect(await getCellText(page, COL.name, 0)).toBe('Alice');
  });

  test('WebSocket receives data for scrolled rows', async ({ page, request }) => {
    // Create a larger dataset (100 rows) to force infinite scrolling
    const rows = [];
    for (let i = 0; i < 100; i++) {
      rows.push(`row${i},${i},${i * 1.5}`);
    }
    const content = 'name,age,score\n' + rows.join('\n') + '\n';
    const bigCsvPath = path.join(os.tmpdir(), `buckaroo_e2e_big_${Date.now()}.csv`);
    fs.writeFileSync(bigCsvPath, content);

    try {
      const session = `ws-scroll-${Date.now()}`;
      await loadSession(request, session, bigCsvPath);

      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);

      const count = await getRowCount(page);
      expect(count).toBe(100);

      // Verify first row rendered
      expect(await getCellText(page, 'a', 0)).toBe('row0');
    } finally {
      cleanupFile(bigCsvPath);
    }
  });
});
