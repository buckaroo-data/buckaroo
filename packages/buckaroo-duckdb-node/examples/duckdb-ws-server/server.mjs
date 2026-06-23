/**
 * DuckDB WebSocket demo server.
 *
 * Stands the new `buckaroo-duckdb-node` backend behind the EXISTING buckaroo
 * server protocol so the browser bundle (`buckaroo/static/standalone.js`)
 * renders a live, DuckDB-backed viewer — infinite scroll, sort, summary stats —
 * with no Python kernel, over a plain WebSocket.
 *
 * Why the legacy framing: `WebSocketModel` delivers each row window as a binary
 * parquet frame paired with an `infinite_resp` JSON frame, pairs them into a
 * `msg:custom` event, and decodes via `parquetRead(buffers[0])`. So the demo
 * sends the raw parquet bytes from `DuckSource.copyToParquet` as that binary
 * frame, which keeps it self-contained. (The production IPC transport instead
 * answers a single JSON message with an inline `parquet_b64` payload, decoded by
 * `decodeDFData(msg.payload, buffers)` from #933 — see ../../src/transport.ts.
 * The backend logic is identical; only the framing differs.)
 *
 * Run:  pnpm demo        (from packages/buckaroo-duckdb-node)
 * Then open the printed http://localhost:8780/ URL.
 */

import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { WebSocketServer } from 'ws';
import { DuckDBInstance } from '@duckdb/node-api';

import { DuckBackend } from '../../dist/index.js';
import { createNodeApiDuckSource } from '../../dist/adapters/nodeApiDuckSource.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT ?? 8780);

// The browser bundle + CSS the buckaroo Python package builds into buckaroo/static.
const STATIC_DIR =
  process.env.BUCKAROO_STATIC ??
  resolve(__dirname, '../../../../buckaroo/static');

const STATIC_FILES = {
  'standalone.js': 'text/javascript',
  'standalone.css': 'text/css',
  'compiled.css': 'text/css',
};

// ---------------------------------------------------------------------------
// Demo dataset — a synthetic table exercising the fidelity-critical types.
// ---------------------------------------------------------------------------

const TABLE = 'demo';
const ROWS = Number(process.env.ROWS ?? 250_000);

const CREATE_SQL = `
  CREATE TABLE ${TABLE} AS
  SELECT
    i                                              AS row_id,
    (9007199254740993 + i)::BIGINT                 AS big_id,        -- BIGINT > 2^53
    (random() * 1000)::DOUBLE                       AS price,
    ((random() * 100) - 50)::DECIMAL(12,4)          AS pnl,
    DATE '2020-01-01' + (i % 1460)::INTEGER         AS trade_date,
    TIMESTAMP '2020-01-01' + to_minutes((i * 7) % 525600) AS ts,
    ['alpha','bravo','charlie','delta','echo'][(i % 5) + 1] AS bucket,
    CASE WHEN i % 11 = 0 THEN NULL
         ELSE 'order-' || lpad(i::VARCHAR, 7, '0') END    AS order_ref,
    (i % 2 = 0)                                     AS is_active
  FROM range(0, ${ROWS}) t(i)
`;

// The statement the backend renders. Any SQL the connection can resolve works.
const BASE_STMT = `SELECT * FROM ${TABLE}`;

// ---------------------------------------------------------------------------
// Legacy-wire adaptation of the backend's transport-agnostic output.
// ---------------------------------------------------------------------------

/** Unwrap a `{format:'json', data}` envelope to a plain array (legacy df_data_dict). */
function unwrapJsonEnvelope(value) {
  if (value && typeof value === 'object' && value.format === 'json') {
    return value.data;
  }
  return value;
}

function toLegacyInitialState(msg) {
  const df_data_dict = {};
  for (const [k, v] of Object.entries(msg.df_data_dict)) {
    df_data_dict[k] = unwrapJsonEnvelope(v);
  }
  return {
    type: 'initial_state',
    protocol_version: 1,
    mode: 'viewer',
    prompt: '',
    metadata: { path: `duckdb://${TABLE}`, rows: msg.df_meta.total_rows },
    df_meta: msg.df_meta,
    df_data_dict,
    df_display_args: msg.df_display_args,
    buckaroo_state: msg.buckaroo_state,
    buckaroo_options: msg.buckaroo_options,
  };
}

// ---------------------------------------------------------------------------
// HTTP: session page + static assets.
// ---------------------------------------------------------------------------

function sessionHtml(sessionId) {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Buckaroo (DuckDB) — ${sessionId}</title>
  <link rel="stylesheet" href="/static/compiled.css">
  <link rel="stylesheet" href="/static/standalone.css">
  <style>
    html, body { margin: 0; padding: 0; width: 100%; height: 100vh; background: #181d1f; }
    body { display: flex; flex-direction: column; }
    #filename-bar { padding: 4px 10px; font-family: sans-serif; font-size: 13px; color: #ccc; background: #222; border-bottom: 1px solid #333; flex-shrink: 0; }
    #filename-bar:empty { display: none; }
    #prompt-bar { padding: 4px 10px; font-family: sans-serif; font-size: 12px; color: #999; background: #222; border-bottom: 1px solid #333; flex-shrink: 0; }
    #prompt-bar:empty { display: none; }
    #root { flex: 1; display: flex; flex-direction: column; min-height: 0; margin-bottom: 20px; }
    .buckaroo_anywidget, .dcf-root, .orig-df, .df-viewer { flex: 1; display: flex; flex-direction: column; min-height: 0; }
    .df-viewer .theme-hanger { flex: 1 !important; overflow: hidden; }
    .flex { display: flex; } .flex-col { flex-direction: column; }
    .orig-df.flex-row { flex-direction: column; }
    .status-bar, .status-bar .theme-hanger { margin-bottom: 0; }
    .df-viewer, .df-viewer .theme-hanger, .df-viewer .ag-root-wrapper { margin-top: 0; }
  </style>
</head>
<body>
  <div id="filename-bar"></div>
  <div id="prompt-bar"></div>
  <div id="root"></div>
  <script type="module" src="/static/standalone.js"></script>
</body>
</html>`;
}

async function serveStatic(req, res, file) {
  const path = join(STATIC_DIR, file);
  if (!existsSync(path)) {
    res.writeHead(404).end(`missing static asset: ${file}`);
    return;
  }
  const body = await readFile(path);
  res.writeHead(200, { 'content-type': STATIC_FILES[file] }).end(body);
}

// ---------------------------------------------------------------------------
// Boot.
// ---------------------------------------------------------------------------

async function main() {
  if (!existsSync(join(STATIC_DIR, 'standalone.js'))) {
    console.error(
      `\n  Browser bundle not found at ${STATIC_DIR}\n` +
        `  Build it first (from the repo root):\n` +
        `    cd packages/js && pnpm build:standalone\n` +
        `  or set BUCKAROO_STATIC to a directory containing standalone.js.\n`,
    );
    process.exit(1);
  }

  // One in-memory DuckDB, one connection, shared by every WS client — the
  // injected-connection model the backend is designed around.
  const instance = await DuckDBInstance.create(':memory:');
  const connection = await instance.connect();
  console.log(`Creating demo table (${ROWS.toLocaleString()} rows)…`);
  await connection.run(CREATE_SQL);
  const source = createNodeApiDuckSource(connection);

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, `http://localhost:${PORT}`);
      if (url.pathname === '/') {
        res.writeHead(302, { location: '/s/demo' }).end();
      } else if (url.pathname.startsWith('/s/')) {
        res
          .writeHead(200, { 'content-type': 'text/html' })
          .end(sessionHtml(decodeURIComponent(url.pathname.slice(3))));
      } else if (url.pathname.startsWith('/static/')) {
        await serveStatic(req, res, url.pathname.slice('/static/'.length));
      } else {
        res.writeHead(404).end('not found');
      }
    } catch (err) {
      res.writeHead(500).end(String(err));
    }
  });

  const wss = new WebSocketServer({ server, path: undefined });
  wss.on('connection', async (ws, req) => {
    if (!req.url?.startsWith('/ws/')) {
      ws.close();
      return;
    }
    // Each client gets its own backend instance over the shared connection.
    const backend = new DuckBackend(source, BASE_STMT);

    try {
      const initial = await backend.initialState();
      ws.send(JSON.stringify(toLegacyInitialState(initial)));
    } catch (err) {
      console.error('initial_state failed:', err);
      ws.close();
      return;
    }

    ws.on('message', async (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        return;
      }
      // Search: re-run with the new term and resend the (filtered) initial_state.
      if (msg.type === 'buckaroo_state_change') {
        const search = msg.new_state?.quick_command_args?.search;
        const term = Array.isArray(search) && search[0] != null ? String(search[0]) : '';
        backend.setSearch(term);
        try {
          const refreshed = await backend.initialState();
          ws.send(JSON.stringify(toLegacyInitialState(refreshed)));
        } catch (err) {
          console.error('search state_change failed:', err);
        }
        return;
      }
      if (msg.type !== 'infinite_request') return; // read-only viewer: ignore the rest

      const args = msg.payload_args ?? {};
      try {
        const resp = await backend.handleInfiniteRequest(args);
        // Re-frame the inline parquet_b64 envelope as the legacy two-frame wire.
        const bytes = Buffer.from(resp.payload.data, 'base64');
        ws.send(
          JSON.stringify({
            type: 'infinite_resp',
            key: resp.key,
            data: [],
            length: resp.length,
          }),
        );
        ws.send(bytes, { binary: true });
      } catch (err) {
        console.error('infinite_request failed:', err);
        ws.send(
          JSON.stringify({
            type: 'infinite_resp',
            key: args,
            data: [],
            length: 0,
            error_info: String(err),
          }),
        );
      }
    });
  });

  server.listen(PORT, () => {
    console.log(`\n  DuckDB buckaroo demo →  http://localhost:${PORT}/\n`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
