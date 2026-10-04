import { test, expect, Page } from '@playwright/test';
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
  execSync(
    `uv run python -c "import pandas as pd; pd.DataFrame({'x':[1,2,3],'y':[4,5,6]}).to_parquet('${parquetPath}')"`,
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

  test('200 + minted session when session is omitted', async ({ request }) => {
    // Headless hosts (Tauri/Electron) call /load without inventing a session
    // ID; the server mints a UUID and returns it. Sessions explicitly passed
    // by callers are honored unchanged (covered above in '200 on valid CSV').
    const resp = await request.post(`${BASE}/load`, {
      data: { path: csvPath },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(typeof body.session).toBe('string');
    expect(body.session.length).toBeGreaterThan(0);
    expect(body.rows).toBe(5);
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
    expect(body.message).toContain("not found");
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
      expect(body.message).toContain("Unsupported");
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
      await expect.poll(() => getRowCount(page), { timeout: 10_000 }).toBe(3);
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
      await expect.poll(() => getRowCount(page), { timeout: 10_000 }).toBe(5);
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

  test('standalone page advertises stats_update on its WebSocket URL', async ({ page, request }) => {
    const session = `ws-caps-${Date.now()}`;
    await loadSession(request, session, csvPath);

    // The server reads capabilities from ?caps= at open, before the client
    // sends anything, so the page has to put them on the URL it connects to.
    const socketUrls: string[] = [];
    page.on('websocket', (socket) => socketUrls.push(socket.url()));
    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    const wsUrls = socketUrls.filter((u) => u.includes(`/ws/${session}`));
    expect(wsUrls).toHaveLength(1);
    expect(new URL(wsUrls[0]).searchParams.get('caps')).toBe('stats_update');
  });

  // Rows-first c4: the standalone page's scheduler. No session the server can
  // build here defers its stats (that needs a xorq expression), so these
  // tests put the pending state on a real session's first frame and answer
  // the page's stats_request themselves. Rows, config and the stats payload
  // all come from the real server.
  async function loadBuckarooSession(request: any, sessionId: string, path: string = csvPath) {
    const resp = await request.post(`${BASE}/load`, {
      data: { session: sessionId, path, mode: 'buckaroo' },
    });
    expect(resp.ok()).toBe(true);
  }

  test('a pending session: the page asks for stats after the first rows, merges the reply and shows them', async ({ page, request }) => {
    const session = `ws-sched-${Date.now()}`;
    await loadBuckarooSession(request, session);

    const order: string[] = [];
    const requests: any[] = [];
    let realStats: unknown;
    await page.routeWebSocket(new RegExp(`/ws/${session}`), (ws) => {
      const server = ws.connectToServer();
      server.onMessage((message) => {
        if (typeof message !== 'string') {
          ws.send(message);
          return;
        }
        const msg = JSON.parse(message);
        if (msg.type === 'infinite_resp') order.push('infinite_resp');
        if (msg.type === 'initial_state' && realStats === undefined) {
          // The first frame as a deferring server sends it: no stats yet.
          realStats = msg.df_data_dict.all_stats;
          msg.df_data_dict.all_stats = [];
          msg.df_meta = { ...msg.df_meta, stats: { status: 'pending', tier: 'schema', gen: 1 } };
          ws.send(JSON.stringify(msg));
          return;
        }
        ws.send(message);
      });
      ws.onMessage((message) => {
        if (typeof message === 'string') {
          const msg = JSON.parse(message);
          if (msg.type === 'stats_request') {
            order.push('stats_request');
            requests.push(msg);
            ws.send(JSON.stringify({
              type: 'stats_update', stats_gen: msg.stats_gen, scope: msg.scope, tier: 'full',
              final: true, payload: realStats, elapsed_ms: 1,
            }));
            return;
          }
        }
        server.send(message);
      });
    });

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // The stats arrive: the status bar says so and the pinned dtype row has its values.
    await expect(page.getByTestId('stats-status')).toHaveAttribute('data-stats-status', 'complete', { timeout: 10_000 });
    await expect(page.locator('.ag-floating-top [col-id="b"]').first()).not.toHaveText('', { timeout: 10_000 });

    // One request, for the gen on the first frame, after rows had arrived: an
    // incremental step carrying the columns the grid shows (rows-first c4b). This
    // harness answers it with a final reply carrying every stat, as a server
    // that does not know the field does, and the page takes that as the end.
    expect(requests).toEqual([{ type: 'stats_request', stats_gen: 1, scope: 'raw', incremental: true, columns: ['a', 'b', 'c'] }]);
    expect(order.indexOf('infinite_resp')).toBeGreaterThanOrEqual(0);
    expect(order.indexOf('infinite_resp')).toBeLessThan(order.indexOf('stats_request'));
  });

  test('a session whose stats are not computed: the page asks for nothing until the Compute summary stats button is clicked', async ({ page, request }) => {
    const session = `ws-notcomputed-${Date.now()}`;
    await loadBuckarooSession(request, session);

    const requests: any[] = [];
    await page.routeWebSocket(new RegExp(`/ws/${session}`), (ws) => {
      const server = ws.connectToServer();
      let firstFrame = true;
      server.onMessage((message) => {
        if (typeof message === 'string') {
          const msg = JSON.parse(message);
          if (msg.type === 'initial_state' && firstFrame) {
            firstFrame = false;
            msg.df_data_dict.all_stats = [];
            msg.df_meta = { ...msg.df_meta, stats: { status: 'not_computed', tier: 'schema', gen: 4, reason: 'host' } };
            ws.send(JSON.stringify(msg));
            return;
          }
        }
        ws.send(message);
      });
      ws.onMessage((message) => {
        if (typeof message === 'string') {
          const msg = JSON.parse(message);
          if (msg.type === 'stats_request') {
            requests.push(msg);
            return;
          }
        }
        server.send(message);
      });
    });

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);
    await expect(page.getByTestId('stats-status')).toHaveAttribute('data-stats-status', 'not_computed');
    // The pinned rows are omitted, not left as placeholders.
    await expect(page.locator('.ag-floating-top .ag-row')).toHaveCount(0);

    // Nothing is asked for on its own, however long the page waits.
    await page.waitForTimeout(2500);
    expect(requests).toEqual([]);

    await page.getByRole('button', { name: 'Compute summary stats' }).click();
    await expect.poll(() => requests).toEqual([
      { type: 'stats_request', stats_gen: 4, scope: 'raw', incremental: true, force: true, columns: ['a', 'b', 'c'] },
    ]);
  });

  // Rows-first c4b: a server on the unit path answers an incremental request
  // with a partial stats_update and expects another request. The harness
  // answers from the test, with the session's real all_stats as the final
  // payload, so no xorq is needed.
  async function routeStatsRequests(
    page: Page,
    session: string,
    onRequest: (msg: any, send: (m: object) => void, h: { realStats: unknown; firstFrame: any }) => void,
  ) {
    const h = { requests: [] as any[], realStats: undefined as unknown, firstFrame: undefined as any };
    await page.routeWebSocket(new RegExp(`/ws/${session}`), (ws) => {
      const server = ws.connectToServer();
      server.onMessage((message) => {
        if (typeof message === 'string') {
          const msg = JSON.parse(message);
          if (msg.type === 'initial_state' && h.realStats === undefined) {
            h.realStats = msg.df_data_dict.all_stats;
            msg.df_data_dict.all_stats = [];
            msg.df_meta = { ...msg.df_meta, stats: { status: 'pending', tier: 'schema', gen: 1 } };
            h.firstFrame = msg;
            ws.send(JSON.stringify(msg));
            return;
          }
        }
        ws.send(message);
      });
      ws.onMessage((message) => {
        if (typeof message === 'string') {
          const msg = JSON.parse(message);
          if (msg.type === 'stats_request') {
            h.requests.push(msg);
            onRequest(msg, (m) => ws.send(JSON.stringify(m)), h);
            return;
          }
        }
        server.send(message);
      });
    });
    return h;
  }
  const partialUpdate = (gen: number, remaining: number) => ({
    type: 'stats_update', stats_gen: gen, scope: 'raw', tier: 'full', final: false, remaining,
    payload: { format: 'json', layout: 'wide', data: [{ index: 'dtype', level_0: 'dtype', a: 'object', b: 'int64', c: 'float64' }] },
    elapsed_ms: 1,
  });

  test('partial updates: the page asks again for each one, keeps the stats pending, and completes on the final', async ({ page, request }) => {
    const session = `ws-incremental-${Date.now()}`;
    await loadBuckarooSession(request, session);

    let releaseFinal!: () => void;
    const finalGate = new Promise<void>((resolve) => { releaseFinal = resolve; });
    const h = await routeStatsRequests(page, session, (msg, send, harness) => {
      if (harness.requests.length <= 2) {
        send(partialUpdate(msg.stats_gen, 3 - harness.requests.length));
        return;
      }
      void finalGate.then(() => send({
        type: 'stats_update', stats_gen: msg.stats_gen, scope: 'raw', tier: 'full', final: true, remaining: 0,
        payload: harness.realStats, elapsed_ms: 1,
      }));
    });

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    // Two partial replies, two more requests, and the third waits for its reply.
    await expect.poll(() => h.requests.length, { timeout: 10_000 }).toBe(3);
    const asked = { type: 'stats_request', stats_gen: 1, scope: 'raw', incremental: true, columns: ['a', 'b', 'c'] };
    expect(h.requests).toEqual([asked, asked, asked]);
    // The partial rows are in, and the stats are still pending: no final yet.
    await expect(page.locator('.ag-floating-top [col-id="b"]').first()).toHaveText('int64', { timeout: 10_000 });
    await expect(page.getByTestId('stats-status')).toHaveAttribute('data-stats-status', 'pending');
    await page.waitForTimeout(500);
    expect(h.requests).toHaveLength(3);

    releaseFinal();
    await expect(page.getByTestId('stats-status')).toHaveAttribute('data-stats-status', 'complete', { timeout: 10_000 });
    await page.waitForTimeout(500);
    expect(h.requests).toHaveLength(3);
  });

  test('the columns hint follows the grid viewport: a wide table sends the columns on screen, and the next request the ones scrolled to', async ({ page, request }) => {
    const wideCsv = path.join(os.tmpdir(), `buckaroo_e2e_wide_${Date.now()}.csv`);
    const names = Array.from({ length: 60 }, (_, i) => `column_${i}`);
    fs.writeFileSync(wideCsv, [names.join(','), names.map((_, i) => String(i)).join(','), names.map((_, i) => String(i * 2)).join(',')].join('\n') + '\n');
    try {
      const session = `ws-incremental-wide-${Date.now()}`;
      await loadBuckarooSession(request, session, wideCsv);

      // Each partial reply waits for the test, so the grid can scroll between requests.
      const replies: Array<() => void> = [];
      const h = await routeStatsRequests(page, session, (msg, send) => {
        replies.push(() => send(partialUpdate(msg.stats_gen, 5)));
      });
      await page.goto(`${BASE}/s/${session}`);
      await waitForGrid(page);

      // The data grid's header cells (the status bar is a grid too).
      const headerIds = () => page.locator('.df-viewer .ag-header-viewport .ag-header-cell[col-id]').evaluateAll(
        (cells) => cells.map((c) => c.getAttribute('col-id') as string));
      await expect.poll(() => h.requests.length, { timeout: 10_000 }).toBe(1);
      const first: string[] = h.requests[0].columns;
      expect(first).toEqual(expect.any(Array));
      // Only the columns on screen, from the left edge: not all sixty.
      expect(first.length).toBeGreaterThan(2);
      expect(first.length).toBeLessThan(40);
      expect(first[0]).toBe('a');
      // The grid may lay out more columns after the first rows, so the hint is
      // the columns it showed at the time: the leading ones.
      expect((await headerIds()).filter((id) => id !== 'index').slice(0, first.length)).toEqual(first);

      // Scroll to the right edge, then let the first reply through. The scroll
      // event is sent by hand each time: the grid may not have been listening
      // for the first one, and setting the same offset again sends none.
      await expect.poll(async () => {
        await page.locator('.df-viewer .ag-body-horizontal-scroll-viewport').evaluate((el) => {
          el.scrollLeft = el.scrollWidth;
          el.dispatchEvent(new Event('scroll'));
        });
        return (await headerIds()).includes('a');
      }, { timeout: 10_000 }).toBe(false);
      const scrolledTo = (await headerIds()).filter((id) => id !== 'index');
      // The grid reports its columns a frame after it renders them: let that pass
      // before the next request can be sent.
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      replies[0]();
      await expect.poll(() => h.requests.length, { timeout: 10_000 }).toBe(2);
      const second: string[] = h.requests[1].columns;
      expect(second).toEqual(expect.any(Array));
      expect(second).not.toContain('a');
      expect(second).toContain(scrolledTo[scrolledTo.length - 1]);
    } finally {
      cleanupFile(wideCsv);
    }
  });

  test('a gen change in the middle of a run: the old gen is dropped and the page asks again for the new one', async ({ page, request }) => {
    const session = `ws-incremental-gen-${Date.now()}`;
    await loadBuckarooSession(request, session);

    const h = await routeStatsRequests(page, session, (msg, send, harness) => {
      if (harness.requests.length === 1) {
        send(partialUpdate(msg.stats_gen, 2));
      } else if (harness.requests.length === 2) {
        // The server moved to gen 2 (a state change) with the run for gen 1
        // in flight; its late reply for gen 1 follows the frame.
        const frame = { ...harness.firstFrame, df_meta: { ...harness.firstFrame.df_meta, stats: { status: 'pending', tier: 'schema', gen: 2 } } };
        send(frame);
        send(partialUpdate(1, 1));
      } else {
        send({
          type: 'stats_update', stats_gen: msg.stats_gen, scope: 'raw', tier: 'full', final: true, remaining: 0,
          payload: harness.realStats, elapsed_ms: 1,
        });
      }
    });

    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);

    await expect(page.getByTestId('stats-status')).toHaveAttribute('data-stats-status', 'complete', { timeout: 15_000 });
    // Two requests for gen 1, then one for gen 2, and none for gen 1 after the change.
    expect(h.requests.map((r) => r.stats_gen)).toEqual([1, 1, 2]);
    expect(h.requests[2]).toMatchObject({ incremental: true, columns: ['a', 'b', 'c'] });
  });

  test('a session that does not report df_meta.stats never gets a stats_request', async ({ page, request }) => {
    const session = `ws-nosched-${Date.now()}`;
    await loadBuckarooSession(request, session);

    const sentTypes: string[] = [];
    page.on('websocket', (socket) => {
      socket.on('framesent', (frame) => {
        if (typeof frame.payload === 'string') sentTypes.push(JSON.parse(frame.payload).type);
      });
    });
    await page.goto(`${BASE}/s/${session}`);
    await waitForGrid(page);
    await expect(page.locator('.status-bar')).toBeVisible();
    // Longer than the scheduler would wait for rows that never come.
    await page.waitForTimeout(3000);

    expect(sentTypes).toContain('infinite_request');
    expect(sentTypes).not.toContain('stats_request');
    await expect(page.getByTestId('stats-status')).toHaveCount(0);
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
