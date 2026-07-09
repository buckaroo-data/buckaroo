# DuckDB/Node backend for buckaroo-js-core

Tracks #930. **Blocked on #933** (unified DF transport) — see "Dependency on
#933" below; that PR removes the only piece that would otherwise force a
buckaroo-js-core change.

## Goal

A first-class DuckDB-backed buckaroo backend that runs in a pure Node/Electron
host with no Python kernel. The JS-core viewer (`DFViewerInfinite`,
`SmartRowCache`, `IDatasource`) renders the same behind DuckDB as it does behind
pandas/polars, because `IModel` is the transport seam and stays untouched.

The motivating consumer is an Electron app (`~/code/aistudio`,
`@duckdb/node-api`, no Python) whose author wants the full notebook experience —
search, infinite scroll, summary stats, histograms. Today it renders a static
`DFViewer` over `SELECT * … LIMIT 101` plus a separate `SUMMARIZE`-to-strings
metadata table; it uses none of the infinite/cache machinery. This backend is
what lets it adopt the real thing.

## Dependency on #933 (unified DF transport)

#933 introduces `decodeDFData(envelope, buffers?) => Promise<DFData>` and a
`DFEnvelope` tagged union (`parquet_buffer` | `parquet_b64` | `json`), and routes
the infinite-scroll path through it. That removes the wrinkle that otherwise
sinks this plan:

- **Today** the infinite path hard-requires two frames. `BuckarooWidgetInfinite.tsx:122`
  does `const table_bytes = buffers[0]` and feeds it straight to `parquetRead`.
  A single JSON message with inline parquet crashes (`buffers[0]` undefined).
- **After #933** the infinite path is `decodeDFData(msg.payload, buffers)`, so a
  backend can answer with a single JSON message whose `payload` is
  `{format:'parquet_b64', data:<base64 parquet>}` — no separate binary frame.

This is decisive for a request/response transport (IPC or HTTP): the DuckDB
backend returns one JSON object, base64 parquet inline, and the `IModel` adapter
is a plain round-trip with no binary-frame synthesis. It also gives us
`parseParquetRow` object/list-cell parsing for free (a latent bug #933 fixes on
the infinite path). **Do not start the row-transport work until #933 lands.**

## Scope

### v1 (this effort)

- Summary stats from DuckDB `SUMMARIZE` → `SDType` → wide `{col}__{stat}` parquet
  for the pinned summary rows.
- Windowed rows + sort + paging over `infinite_request`.
- `viewer` mode. Read-only: no autocleaning, no post-processing, no search, no
  quick commands. `buckaroo_state_change` is a no-op stub.
- `IModel`-over-IPC adapter; no websocket; no buckaroo-js-core change.
- Injected `DuckSource` connection; core ships zero native bindings.

### Fast-follow (designed-for, not built)

- **Histograms / quantiles** — `histogram_bins`, `histogram_log_bins`, the
  numeric/categorical histogram, exact-or-approx quantiles. This is the bulk of
  the SQL-porting work (the `customizations/xorq_stats_v2.py` parity set) and the
  author explicitly wants it, but it deserves its own focused pass after the
  transport is proven.
- **Search** — and not the row-only filter the Python *server* uses. That split
  (`data_loading.py` filters rows per-client, stats stay whole-dataset) was an
  expedient hack around xorq's slowness, not an architectural choice. The broader
  design is: search produces a parallel `search_`-prefixed stat set
  (`search_mean`, `search_min`, …) over the filtered rows, shown alongside the
  full-dataset stats. No backend implements that today — and DuckDB is the
  natural first one to, because the reason it doesn't exist (re-aggregating
  filtered stats per keystroke is too slow) doesn't apply to DuckDB. Search =
  "run the stats step a second time over `effectiveQuery + WHERE`, prefix the
  keys."
- **Quick commands** — per-command SQL translation, graded steeply: Search /
  DropCol / FillNA are trivial; `GroupBy` is the monster (dict agg-spec across
  40+ aggregation functions, `count_null` special case, shape-changing).
  aistudio should translate the handful it wants, not all ~22.
- **Exact DECIMAL** — v1 casts `DECIMAL → DOUBLE` (see type map); exactness is
  tracked separately in #934 (likely affects all backends, not just DuckDB).

## Architecture

### Transport — `IModel` over IPC, no socket, no JS-core change

aistudio has no Node webserver; it is Electron main + renderer over IPC
(`ipcMain.handle`/`ipcRenderer.invoke`). buckaroo-js-core runs in the renderer
and can't call native DuckDB bindings, which live in main.

A custom `IModel` adapter (renderer side) maps `model.send(msg)` →
`ipcRenderer.invoke('buckaroo:msg', msg)` → main answers → adapter
`emit("msg:custom", reply)`. The "two frames" of `WebSocketModel` is a
`WebSocketModel` implementation detail; the React handler only needs the
`"msg:custom"` event. Post-#933 the reply is a single JSON object with inline
`parquet_b64`, so no binary frame and no buffers array are needed.

No websocket: a single embedded client needs no server push. `initial_state` is
one round-trip; sort/paging are request/response. (A websocket companion remains
a *secondary* altitude for non-Electron Node hosts; not in scope here.)

### Serialization — `COPY` → tempfile parquet (the only no-coercion path)

`@duckdb/node-api@1.4.4-r.3` has **no Arrow output** and **no in-memory parquet**
(verified against its `.d.ts` + README); parquet is writable only via SQL
`COPY … TO '<file>' (FORMAT PARQUET)`. Native-type accessors hand back DuckDB
wrapper objects (`DuckDBDecimalValue{value:bigint,scale}`, `DuckDBDateValue`,
`bigint`).

The hard rule is **buckaroo writes no type-coercion code** — coercion is where
fidelity bugs live (the aistudio status quo coerces `BigInt`→`Number`, lossy
above 2^53). The only path satisfying that rule with this API:

```
COPY (<renamed, windowed, sorted query>) TO <tmpfile> (FORMAT PARQUET)
  → read bytes → base64 → {format:'parquet_b64'} envelope → hyparquet (decodeDFData)
```

DuckDB serializes all types natively; we never touch a `DuckDBValue`. The cost
is a temp parquet file per `infinite_request` window — tiny (KB), but it is
filesystem I/O on the scroll hot path and needs unique-naming + cleanup. The
alternatives all reintroduce hand-written coercion (`getColumns()` → a JS
parquet writer) or are lossy (`getRowObjectsJS()` → JSON) — rejected. If
`@duckdb/node-api` gains Arrow later, swap the `copyToParquet` impl behind the
interface; nothing else changes.

### Column renaming — faithful `a,b,c` + synthesized `index`

buckaroo-js-core is agnostic to the `a,b,c` form (it only needs
`column_config.col_name` to equal the row-object keys), but raw DuckDB column
names break it in three ways, all *more* likely from user SQL than from a
DataFrame:

1. A column literally named `index` (or `level_0`) is catastrophic — `index` is
   buckaroo's reserved key (`extractSDFT`, `extractPinnedRows`, `parseParquetRow`
   all match stat/pinned rows by `{index: …}`). DuckDB has no implicit index, so
   the backend must synthesize one anyway (`ROW_NUMBER() OVER () - 1 AS index`),
   and a user column named `index` then collides. `SELECT 1 AS index` is legal.
2. Dotted names (`price.usd`) — ag-grid `field` is set directly to `col_name`
   with no `valueGetter`; dotted fields are a foot-gun.
3. Duplicate names from `SELECT * FROM a JOIN b` collapse to one JS object key →
   silent data loss.

Renaming kills all three and matches the contract the JS already speaks (sort
arrives as the renamed `"a"`). Mechanism: `DESCRIBE (<stmt>)` → ordered
`(name,type)` → project `SELECT col0 AS a, col1 AS b, …, (ROW_NUMBER() OVER ())-1
AS index FROM (<stmt>)`, keep the `{a→origname}` map for `column_config.header_name`
and to reverse the incoming sort column.

### Stats — `SUMMARIZE` → `SDType` (v1)

| buckaroo stat | SUMMARIZE source |
|---|---|
| dtype / typing | `column_type` |
| `min` / `max` | `min` / `max` |
| `distinct_count` | `approx_unique` |
| `mean` / `std` | `avg` / `std` |
| `null_count` | `count × null_percentage` (derived) |
| quantiles | `q25 / q50 / q75` (approx) |
| histogram_bins / log_bins | **— not in SUMMARIZE → fast-follow** |

The package supplies a `df_display_args` whose pinned-row config references only
the stats above, so no row renders empty in v1; histogram rows are added when the
fast-follow SQL lands. Serialize as the wide `{col}__{stat}` parquet via the
`layout:'wide'` envelope.

### Type → displayer map

`INT*/BIGINT → integer`, `DOUBLE/REAL/DECIMAL(cast) → float`, `VARCHAR → string`,
`BOOLEAN → string`, `DATE/TIMESTAMP* → datetime`, everything else → `string`.

### Package boundary — injected `DuckSource`

Core takes an injected connection and imports zero native bindings. This is not
just cleaner; for aistudio it is required for correctness: it runs arbitrary user
SQL against a live connection with attached databases / registered files / temp
views, and the stats/rows queries (`COPY (SELECT … FROM (<stmt>))`) only resolve
in that same catalog. A self-owned connection is a different database that can't
see the user's tables. Injection also avoids a duplicate native addon in the
Electron bundle and decouples buckaroo from node-api's (pre-stable) version.

```ts
interface DuckSource {
  describe(stmt: string): Promise<Array<{ name: string; type: string }>>;
  summarize(stmt: string): Promise<SummarizeRow[]>;
  copyToParquet(query: string): Promise<Uint8Array>; // COPY … TO tmpfile, read bytes
}
```

Ship a batteries-included `@duckdb/node-api` adapter alongside (optional peer
dep) so simpler embedders get a one-liner; aistudio injects its own connection.

The package owns the buckaroo-specific logic aistudio should not reinvent: the
`DESCRIBE`→`a,b,c`+`index` rename, the `SUMMARIZE`→`SDType`→wide-parquet stats,
the `infinite_request`→windowed-SQL translation, the type→displayer
`column_config`, and the `IModel`-over-IPC adapter.

### Effective-query seam (keeps search + quick commands possible)

Model the source as `effectiveQuery(baseStmt, transforms[])`. `DESCRIBE`+rename,
stats, and row-windowing all route through it — never off raw `stmt`. v1's
transform list is empty (sort/paging are per-request window params, not
transforms). This single seam is what makes search (`+ WHERE`, re-run stats for
`search_` keys) and shape-changing quick commands (re-`DESCRIBE`, recompute
stats) clean fast-follows rather than rewrites. Don't strip `quick_command_args`
at the adapter; v1 treats unknown verbs as no-ops.

## The spike — prove transport before stats parity

First, end to end, before any histogram SQL:

1. **Serialization fidelity + latency** — `COPY` 101 rows of mixed
   `BIGINT > 2^53`, `DECIMAL(38,9)`, `DATE`, `TIMESTAMP`, `NULL` → tmpfile parquet
   → base64 → hyparquet → `DFData`. Confirm fidelity *and* measure the per-window
   `COPY`→read round-trip. If temp-file latency disappoints, the fallback is a
   ramdisk/`/dev/shm` path or a future Arrow API — **not** a hand-rolled JS
   coercion layer.
2. **Transport** — `IModel`-over-IPC adapter answering one `infinite_request` with
   a `parquet_b64` envelope (depends on #933).
3. **Stats round-trip** — `SUMMARIZE` → wide parquet → pinned rows render.

## Contract checklist (what the Node backend must satisfy)

- `initial_state` with `df_meta.total_rows`, `df_display_args` (column_config),
  `df_data_dict` (`main: []`, stats as `parquet_b64`/`layout:'wide'` envelope),
  `mode:'viewer'`, `buckaroo_state`.
- `infinite_request` → `{type:'infinite_resp', key, length, payload:{format:'parquet_b64', data}}`
  where `length` is the (filtered, = total in v1) row count and `payload` decodes
  via `decodeDFData`.
- Renamed columns `a,b,c…` + synthesized `index`; sort arrives as renamed name and
  maps back via the rename map.
- Stats as `SDType` (`Dict[col, Dict[stat, val]]`), wide-parquet serialized.

## Open questions

- Temp-file-per-window latency acceptable, or push to ramdisk path? (spike
  measures.)
- Exact-vs-approx distinct/quantiles by row count — reuse #911's threshold and
  #918's dtype routing when the histogram fast-follow lands; don't invent policy.
- Package name / location (`packages/buckaroo-duckdb-node/`).

Relates to #911, #918, #923, #934. Blocked on #933.
