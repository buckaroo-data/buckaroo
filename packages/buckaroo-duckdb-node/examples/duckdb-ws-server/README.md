# DuckDB WebSocket demo server

A runnable demo that stands the `buckaroo-duckdb-node` backend behind a live
browser viewer — infinite scroll, sort, and summary stats over a 250k-row DuckDB
table, no Python kernel.

## Run it

From `packages/buckaroo-duckdb-node`:

```bash
pnpm install          # once, from packages/
pnpm demo             # builds the package, then starts the server
```

Then open **http://localhost:8780/**.

Scroll the grid (rows stream in on demand), click a column header to sort, and
read the pinned summary-stats rows (dtype, null_count, distinct_count, mean,
std, min, q25/q50/q75, max).

Knobs (env vars):

| var | default | meaning |
|---|---|---|
| `PORT` | `8780` | HTTP + WS port |
| `ROWS` | `250000` | synthetic table size |
| `BUCKAROO_STATIC` | `../../../../buckaroo/static` | dir holding the browser bundle |

## Prerequisite: the browser bundle

The demo reuses buckaroo's existing browser bundle (`standalone.js` + CSS),
which the Python package builds into `buckaroo/static/`. If `pnpm demo` reports
it's missing, build it from the repo root:

```bash
cd packages/js && pnpm build:standalone
# (or ./scripts/full_build.sh)
```

## How it renders today (without #933)

The viewer's transport (`WebSocketModel`) delivers each row window as a **binary
parquet frame** paired with an `infinite_resp` JSON frame, then decodes it via
`parquetRead(buffers[0])`. So this server sends the raw bytes from
`DuckSource.copyToParquet` as that binary frame — the exact wire today's
buckaroo-js-core already speaks. No `decodeDFData` (#933) needed.

The backend logic is identical to the production IPC transport
(`src/transport.ts`); only the framing differs. Post-#933, the same
`DuckBackend.handleInfiniteRequest` answer (a single JSON message with an inline
`parquet_b64` payload) flows straight through over Electron IPC with no
re-framing.

## What it exercises

- `DESCRIBE` → `a,b,c…` rename + synthesized `index`
- `SUMMARIZE` → `SDType` → pinned stat rows
- `infinite_request` → sorted/windowed/renamed SQL → `COPY` → parquet
- Serialization fidelity: a `BIGINT > 2^53` column (`big_id`) round-trips
  exactly; `DATE`/`TIMESTAMP`/`NULL` preserved; `DECIMAL` shown as double (the
  documented v1 limitation).
