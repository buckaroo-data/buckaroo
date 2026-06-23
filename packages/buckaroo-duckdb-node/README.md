# buckaroo-duckdb-node

A DuckDB-backed buckaroo backend for pure Node / Electron hosts — no Python
kernel. It produces the same wire payloads (`initial_state`, `infinite_resp`,
wide summary stats) that `buckaroo-js-core`'s `DFViewerInfinite` already speaks,
so the viewer renders behind DuckDB exactly as it does behind pandas/polars.

Tracks [#930](https://github.com/buckaroo-data/buckaroo/issues/930). See
`docs/plans/930-duckdb-node-backend.md`.

## Status (v1)

Implemented and tested:

- **Column rename** — `DESCRIBE` → buckaroo's `a, b, c…` space + a synthesized
  `index` (base-26 scheme matching `df_util.py:to_chars`). Removes the
  `index`-collision, dotted-name, and duplicate-name foot-guns.
- **Windowed rows** — `infinite_request` → sorted, windowed, renamed SQL.
- **Summary stats** — `SUMMARIZE` → `SDType` → the pinned stat rows the viewer
  consumes (dtype, null_count, distinct_count, mean, std, min, q25/q50/q75, max).
- **Type → displayer** config with `DefaultMainStyling` parity.
- **Serialization** — the `COPY → tempfile parquet` no-coercion path, plus a
  batteries-included `@duckdb/node-api` adapter.
- **Transport** — an `IModel`-over-IPC adapter for Electron (renderer ⇄ main).

### Blocked / fast-follow

- **End-to-end rendering is partially blocked on #933.** The producer side here
  is complete, but the renderer decodes the inline `parquet_b64` row payload via
  `decodeDFData` from #933 (unified DF transport). Until that lands in
  `buckaroo-js-core`, the infinite path still does `parquetRead(buffers[0])` and
  cannot consume a single-JSON-message inline-parquet reply. Don't ship the
  renderer integration before #933.
- **Histograms / quantiles, search, quick commands, exact DECIMAL** — designed
  for (the effective-query seam is in place) but not built. See the plan.

## Architecture

```
DuckSource (injected connection)
   describe(stmt)        DESCRIBE → (name, type)[]
   summarize(stmt)       SUMMARIZE → SummarizeRow[]
   copyToParquet(query)  COPY … TO tmpfile (FORMAT PARQUET) → bytes
        │
        ▼
DuckBackend (transport-agnostic)
   initialState()              → initial_state message
   handleInfiniteRequest(args) → infinite_resp { payload: parquet_b64 }
        │
        ▼
IpcDuckModel / makeIpcMainHandler   (Electron IModel-over-IPC)
```

Core imports zero native bindings. Embedders inject a `DuckSource` bound to
*their* live connection (so attached DBs / registered files / temp views
resolve), or use the bundled adapter.

## Usage

```ts
import { DuckBackend } from 'buckaroo-duckdb-node';
import { createNodeApiDuckSource } from 'buckaroo-duckdb-node/node-api';
import { DuckDBInstance } from '@duckdb/node-api';

const instance = await DuckDBInstance.create(':memory:');
const connection = await instance.connect();
const source = createNodeApiDuckSource(connection);

const backend = new DuckBackend(source, 'SELECT * FROM my_table');
const initial = await backend.initialState();
const window = await backend.handleInfiniteRequest({
  sourceName: 'main', start: 0, end: 100, origEnd: 100,
});
```

### Electron

```ts
// main process
import { ipcMain } from 'electron';
import { makeIpcMainHandler } from 'buckaroo-duckdb-node';
ipcMain.handle('buckaroo:msg', makeIpcMainHandler(backend));

// renderer process
import { IpcDuckModel } from 'buckaroo-duckdb-node';
const model = new IpcDuckModel((channel, msg) => ipcRenderer.invoke(channel, msg));
// hand `model` to the buckaroo-js-core viewer (post-#933)
```

## Serialization fidelity (spike findings)

From `test/spike.duckdb.test.ts` (per-101-row window: COPY ≈ 3 ms, read ≈ 5 ms —
temp-file latency is negligible, no ramdisk needed):

| DuckDB type | parquet | hyparquet decode | v1 fidelity |
|---|---|---|---|
| `BIGINT` (incl. > 2^53) | INT64 | `bigint` | exact |
| `DATE` / `TIMESTAMP` | INT32 / INT64 | `Date` | exact instant |
| `VARCHAR`, `NULL` | — | `string` / `null` | exact |
| `DECIMAL(38,9)` | DECIMAL | `number` (double) | lossy — `#934` |
| `HUGEINT` | DOUBLE | `number` | lossy > 2^53 |

## Develop

```bash
pnpm install          # from packages/
pnpm test             # vitest (pure-logic + DuckDB spike)
pnpm build            # tsc → dist/
```

The DuckDB spike requires the optional `@duckdb/node-api` peer; set
`SKIP_DUCKDB=1` to skip it.
