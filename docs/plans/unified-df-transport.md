# Unified DataFrame Transport

## Goal

One place — on each side of the wire — that owns "how a dataframe payload is
encoded and decoded." Today the concern is smeared across `resolveDFData.ts`,
the bare `parquetRead` in `BuckarooWidgetInfinite.tsx`, three duplicated Python
`infinite_resp` senders, `sd_to_parquet_b64`, and `_df_to_parquet_b64_tagged`.
After this change, every dataframe (main table **or** summary stats) — across
`DFViewer`, `DFViewerInfinite`, `BuckarooInfiniteWidget`, `DFViewerInfiniteDS`
— flows through a single decode function on the JS side and a single encode
function on the Python side.

## The envelope

A tagged discriminated union. `format` is the discriminator. Bytes either ride
inline (`parquet_b64`/`json`) or in a comm side-channel buffer
(`parquet_buffer`), addressed by `buffer_index`.

```ts
// DFWhole.ts — replaces ParquetB64Payload / DFDataOrPayload
export type DFEnvelope =
  | { format: 'parquet_buffer'; buffer_index: number; layout?: 'wide' } // parquet bytes in buffers[]
  | { format: 'parquet_b64';    data: string;        layout?: 'wide' } // base64 parquet, inline
  | { format: 'json';           data: DFData;        layout?: 'wide' };// record array, inline

export type DFDataOrPayload = DFData | DFEnvelope; // DFData passthrough retained
```

- `format` — key name kept as `format` (matches today's field).
- values: `parquet_buffer` / `parquet_b64` / `json`. Names are self-describing:
  `parquet_b64` is unchanged from today (so existing payloads and persisted
  artifacts keep loading with no alias); the buffer value carries parquet too,
  hence `parquet_buffer`; `json` carries record arrays, not parquet, so no prefix.
  There is no `b64`-vs-`parquet_b64` distinction in practice — base64 only ever
  wraps parquet here — so the more precise existing name wins and no legacy alias
  is needed.
- `buffer_index` — required for `parquet_buffer`; a single comm message can carry
  several dataframes (main + summary stats), so the decoder must know which
  buffer is which.
- `layout` — orthogonal to transport. `'wide'` means the decoded parquet is the
  single-row `{col}__{stat}` summary-stats shape and must be pivoted. Applies to
  `parquet_buffer` and `parquet_b64`. Carried on the envelope, not baked into the
  format.

## JS side — one decoder, awaited only at ingestion edges

```ts
// resolveDFData.ts (or new transport.ts) — THE one place
export async function decodeDFData(
  env: DFDataOrPayload | null | undefined,
  buffers?: DataView[],
): Promise<DFData>
```

Branches:
- `null`/`undefined` → `[]`; `Array.isArray` → passthrough (already `DFData`).
- `parquet_buffer` → `parquetBytes = buffers[env.buffer_index]` → `parquetRead` → rows.
- `parquet_b64` → `atob` → bytes → `parquetRead` → rows.
- `json` → `env.data` rows.
- then, for parquet-derived rows: `layout==='wide'` → `pivotWideSummaryStats`,
  else `rows.map(parseParquetRow)`. `json` rows pass through (already typed).

`parseParquetRow` / `pivotWideSummaryStats` / the b64 helper / the BigInt
helpers all move behind `decodeDFData` and stop being called anywhere else.

### Async is contained to ingestion — no `await` in the component tree

The interface is `Promise<DFData>`, but it is only awaited where data *enters*
the system. Components keep receiving plain `DFData` and stay synchronous.
Three ingestion edges:

1. **Infinite comm handler** — `getKeySmartRowCache` `model.on("msg:custom", …)`
   in `BuckarooWidgetInfinite.tsx:102`. Already a callback. Replace the bare
   `parquetRead` (lines 122–135) with
   `decodeDFData(msg.payload ?? msg, buffers).then(d => { resp.data = d; src.addPayloadResponse(resp) })`.
   The Python sender now puts a `parquet_buffer` envelope on the message instead of
   relying on the untagged-`buffers[0]` convention.

2. **`df_data_dict` trait** — main static + summary stats. One hook decodes the
   dict whenever the trait changes and stores decoded `DFData` in state
   (generalizes today's `preResolveDFDataDict`). `BuckarooInfiniteWidget` /
   `DFViewerInfiniteDS` consume the decoded dict; `summary_stats_data` prop type
   becomes `DFData` (was `DFDataOrPayload`). Downstream `resolveDFData` calls
   inside components are deleted.

3. **Static HTML-embed mount** — decode once before mounting the React root.

After this, prop types in the component tree are `DFData` end-to-end; the
fragile synchronous `resolveDFData` (returns `[]` in some bundlers) is deleted.

## Python side — one encoder, capability-driven

```python
# serialization_utils.py — THE one place
def encode_df(df, transport, *, layout=None, fmt=None) -> tuple[dict, list[bytes]]:
    """Return (envelope_dict, buffers). buffers is [] unless fmt resolves to 'parquet_buffer'."""
```

Format driver = **transport capability + override**:
- `transport='comm'` (anywidget/websocket/zmq, binary buffers OK) → `parquet_buffer`:
  returns `({'format':'parquet_buffer','buffer_index':i, **layout}, [to_parquet(df)])`.
- `transport='static'` (HTML embed, no side-channel) → `parquet_b64`:
  returns `({'format':'parquet_b64','data':to_parquet_b64(df), **layout}, [])`.
- `fmt='json'` (explicit; typing-tolerant / tiny / debugging) → `json`:
  returns `({'format':'json','data':pd_to_obj(df), **layout}, [])`.
- `fmt` overrides the capability default when given.

Summary-stats wide encoding folds in: `sd_to_parquet_b64` becomes
`encode_df(wide_df, transport, layout='wide')` (or a thin wrapper that builds
the wide pyarrow table then hands bytes to the envelope builder). The
`{col}__{stat}` table construction in `sd_to_parquet_b64` is preserved; only the
envelope wrapping is unified.

### Consolidate the three senders

`buckaroo_widget.py:423`, `polars_buckaroo.py:129`, `xorq_buckaroo.py:355` each
hand-build `{"type":"infinite_resp", 'key':…, 'data':[], 'length':…}` +
`[to_parquet(slice)]` (xorq via its `window_to_parquet` helper, not `to_parquet`
directly). Replace each with a shared helper that calls
`encode_df(slice, 'comm')` and sends
`{"type":"infinite_resp", 'key':…, 'length':…, "payload": envelope}` plus the buffers.
`_df_to_parquet_b64_tagged` (artifact.py) becomes `encode_df(df, 'static')`.

## Latent bug this fixes (needs a test)

The infinite buffer path (`BuckarooWidgetInfinite.tsx:128–131`) casts hyparquet
output directly to `DFData` and never runs `parseParquetRow`, so JSON-encoded
object/list/dict cells in the **main** table are not parsed back — while the b64
static path *does* parse them (`decodeParquetRows`). Routing both through
`decodeDFData` makes the infinite path parse object cells too. A main-table
dataframe with a list/dict column, fetched over the infinite path, currently
renders the raw JSON string; after unification it renders the parsed value.

## TDD sequence (per repo rules: failing tests on CI first, then fixes)

Commit 1 — **failing tests** (bundled, one commit):
- JS: `decodeDFData` unit tests over all inputs (`parquet_buffer`,
  `parquet_b64`, `json`, plain `DFData` passthrough) incl. `layout:'wide'` pivot
  and the object-cell JSON-parse for the buffer path. Reference fixtures from
  `resolveDFData.test.ts`.
- JS: infinite path renders parsed object/list cells (the latent-bug test).
- Python: `encode_df` round-trips each `(transport, fmt)` → expected envelope
  shape + buffer presence; `resolve_summary_stats_payload` / `_pivot_wide_sd_row`
  still decode wide payloads built via the new encoder.
Push, watch CI fail.

Commit 2+ — **fixes**:
- Add envelope types + `decodeDFData`; delete sync `resolveDFData`.
- Wire the 3 JS ingestion edges.
- Add `encode_df`; refactor the 3 senders + summary stats + artifact onto it.
- Run `pnpm test`, `pnpm test:pw`, `pytest tests/unit/`, full build locally.
Push, watch CI pass.

## Message shape: nest the envelope under `payload` (decided)

`infinite_resp` (and every future comm message that carries a dataframe) nests
the envelope under a dedicated `payload` key, kept separate from the message's
routing/semantic fields:

```python
self.send({"type":"infinite_resp", "key":pa, "length":n,
           "payload":{"format":"parquet_buffer", "buffer_index":0}}, [bytes])
```
```ts
resp.data = await decodeDFData(msg.payload, buffers);  // msg.payload IS a bare DFEnvelope
```

Rationale — every `decodeDFData` call site receives a clean bare `DFEnvelope`:
`df_data_dict[key]` values are already bare envelopes, and `msg.payload` is too.
One input type everywhere; cache-protocol fields (`key`/`length`/`error_info`)
stay out of the decoder where they belong (they're `SmartRowCache`'s concern,
not "how are the bytes encoded"). The stale `data:[]` placeholder is dropped.

### Forward-compat with the PR #719 cache redesign (the deciding factor)

PR #719 (merged) replaces the single `infinite_resp` with **three** message
kinds, only one of which carries rows (`buckaroo/row_cache_payloads.py`):

| kind | decoded parquet | semantic fields |
|---|---|---|
| `populate` | full rows **+** `_buckaroo_rowid` | `{rowids, rows}` |
| `sort` | `_buckaroo_rowid` only | `{rowidOrder}` |
| `filter` | `_buckaroo_rowid` only | `{rowidSubset}` |

A `sort`/`filter` response is a rowid permutation, **not** a row payload — so
the "message *is* the rows, spread the envelope onto it" framing breaks the
moment phase 7c lands. Nesting makes the envelope a reusable thing any message
kind attaches, and `decodeDFData(msg.payload, buffers)` is the **one transport
primitive** ("parquet bytes → row objects") shared across `infinite_resp`,
`populate`, `sort`, `filter`, and the `df_data_dict` path. Spread would force
each new 7c message kind to re-flatten `format`/`buffer_index` into its own top
level — work that 7c would then have to unpick for the rowids-only kinds. So
nesting isn't only cleaner today; it's the shape 719's unfinished work needs.

Notes for whoever lands 7c (tracked, not blockers here):
- `make_populate_payload` ships `_buckaroo_rowid` *inside* the same parquet
  table as the data, so `decodeDFData` stays a pure bytes→rows primitive and
  rowid extraction is a `RowCache`-controller concern layered on top.
- The 719 builders use plain `pq.write_table`, whereas `to_parquet` uses
  fastparquet with `object_encoding='json'` for object/category columns — the
  same JSON-encoded-object-cell convention `parseParquetRow` relies on. When
  `encode_df` eventually becomes the single producer behind the row_cache
  builders too, that object-cell convention must stay consistent or the decoder
  will mis-handle one path.

## Open / to confirm during implementation

- Whether `DFViewer` (the static, synchronous artifact entry) should accept an
  envelope at all or only ever pre-decoded `DFData` (push decode to its mount).
