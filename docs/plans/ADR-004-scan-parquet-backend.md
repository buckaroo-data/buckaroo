# ADR: An out-of-core `scan_parquet` backend for polars `/load`

- **Status:** Proposed (2026-10-06). The decisions below are recommendations and 8 are open for the maintainer (see "Open decisions"). Nothing here is implemented on main. #1011 (closed) prototyped an earlier shape of D1, D3, D5 and the stats half of D8, and its measurements are used below.
- **Affected code:** `buckaroo/server/data_loading_polars.py` (`load_file_polars`, `PolarsServerSampling`, `PolarsServerDataflow`, `handle_infinite_request_buckaroo_polars`), `buckaroo/server/data_loading.py` (`load_file_lazy`, `handle_infinite_request_lazy`), `buckaroo/server/handlers.py` (`/load`), `session.py`, `buckaroo/customizations/pl_stats_v2.py` and a lazy stats executor, `buckaroo/server/window.py`.
- **Related:** #992 (windows over a shuffled 1M-row sample), #993 (whole file in memory per session), #995 (no row-order tie-break), #999 (polars stats in one select), #1000 and #1005 (closed: eager stopgaps), #1011 (closed: lazy prototype), ADR-001 (stat cache), ADR-002 (stats delivery), ADR-003 (stat tiers; its "Not decided here" names this backend).

## Terms

- **scan session**: a `/load` session that holds a `pl.LazyFrame` over a parquet file and never materializes the table.
- **key phase**: a query over the row index and the sort key only, so its cost follows two columns.
- **gather phase**: reading the full rows for a list of row indices.
- **window**: the rows `start:end` of the filtered, sorted view that an `infinite_request` asks for.

## Problem

The destination for polars `/load` is out-of-core: hold a scan, read only what a request needs. #1000 (`pre_limit=False`) and #1005 (a shared eager frame) were closed on that basis. Three things exist on main or in a closed PR, and none of them gets there.

**Eager `backend="polars"`** reads the file with `pl.read_parquet` and keeps the frame per session (#993). RSS is 0.28 GB + 0.543 GB per million rows, so 78M rows is about 42.6 GB by the fit, for one session. Above 1M rows `PolarsServerSampling.pre_limit` replaces the frame with a shuffled 1M-row sample before anything runs, so sort and search answer over the sample (#992).

**`mode="lazy"`** (`load_file_lazy`, `handle_infinite_request_lazy`) holds a `LazyFrame` and has no stats, no search, and sorts the whole frame: `lf.sort(col).slice(100, 100).collect()` on a 12M x 43 file took 1.64 s and peaked at 14.56 GB (3.03 s and 10.51 GB with `engine="streaming"`).

**#1011** (closed) added stats and search to a lazy session. On the 78M x 43 tallyman entry, `/load` took 2.4 s and 2.0 GB, an unsorted window 5 to 16 ms, a window sorted by a string column 12.3 to 23.2 s, a search for `NY` 10.0 to 18.3 s per request (3.0 s when nothing matches), and across three rounds of the same six requests the per-round maximum RSS rose from 9.6 GB to 11.1 GB to 14.5 GB. On the 12M slice, RSS levelled off at 8.5 to 10.2 GB, above eager main's 7.3 to 9.1 GB, and a searched window took 0.93 to 1.34 s.

A scan holds almost no memory at rest. The cost is per request: sort and search read every column, and memory follows the number of columns read rather than the size of the answer.

## Measurements

One 12M x 43 parquet file (351 MB, 46 row groups of 262,144 rows, 29 string columns), polars 1.35.2, Apple M4 Pro, load average 4.6, one fresh process per row, single run. Peak RSS is `ru_maxrss`. macOS compresses idle pages, so RSS can under-read. The probe script and its output are in a comment on the PR.

| request | time | peak RSS |
|---|---|---|
| `count` | 0.01 s | 0.07 GB |
| window 0:100, and 6,000,000:6,000,100 | 0.02 s | 0.08 GB |
| whole-frame sort on a string column, window 100:200 (default engine) | 1.64 s | 14.56 GB |
| same, `engine="streaming"` | 3.03 s | 10.51 GB |
| whole-frame `top_k(200)`, numeric / string key | 1.13 s / 0.41 s | 6.08 / 7.45 GB |
| `top_k(200)` over row index and key only, numeric / string key | 0.02 s / 0.03 s | 0.26 / 0.46 GB |
| sort of row index and string key only, all 12M indices | 0.60 s | 1.22 GB |
| #1011's two-pass sort (key sort, then `filter(index.is_in(...))`), numeric / string | 0.53 s / 1.00 s | 7.52 GB |
| gather 100 random rows, one `slice(i, 1)` collect per row | 1.24 s | 0.34 GB |
| gather 100 random rows, `concat` of the 100 slices in one collect | 0.47 s | 7.50 GB |
| search all 29 string columns, count only (streaming) | 0.41 s | 5.42 GB |
| search all 29 string columns, first 100 matches (streaming / default) | 0.29 s / 0.48 s | 5.14 / 7.98 GB |
| search one column for a rare term (13 matches), first 100 | 0.06 s | 0.58 GB |
| search all columns in 262,144-row chunks, count only | 1.59 s | 2.21 GB at the end |
| search all columns in 1,000,000-row chunks, count only | 0.96 s | 2.95 GB at the end |

The two chunked rows report current RSS at the end of the run (`ps`), which had stopped rising by the middle chunk; the others report the peak. At 78M rows the stats probes ran as follows: scalars plus approximate distinct in 2.6 s and 4.9 GB, exact distinct in 4.4 s and 13.7 GB, and approximate distinct plus median, tails and histogram in 34.2 s and 18.3 GB.

What these show:

- Anything that touches one or two columns is cheap and small. Anything that touches all columns peaks at 5 to 15 GB at 12M rows whatever the engine.
- #1011's two-pass sort moved the sort onto two columns, but its second pass filters the whole scan by `is_in` and read every column again (7.52 GB). The key phase is the part worth keeping.
- Concatenating many one-row slices into one query reads everything (7.50 GB). Collecting each slice separately keeps memory at 0.34 GB and costs 12 ms per row.
- Chunking the search lowers memory about 2x and raises time 2 to 4x. It does not bound memory.

## Decisions

### D1. A parquet `/load` on the polars backend opens a scan session

`backend="polars"` with a `.parquet` path holds `pl.scan_parquet(path)` and the file's footer metadata. No eager frame exists on the session, and `pre_limit` does not apply, so windows answer over the whole file and #992 ends for parquet. CSV, TSV and ndjson are not covered: the only CSV measurements here are on xorq, where each query reparses the file (2.1 to 2.2x for column-chunked batches). They keep the eager path. `mode="lazy"` and the polars backend converge on one implementation, and `mode="lazy"` keeps its name.

### D2. Load costs a footer read

Schema, row count and row-group boundaries come from the footer. `count` was 10 ms at 12M rows and footer open and parse about 1 ms at 40 row groups (ADR-003 D10). `/load` returns before any scan, with the schema tier from ADR-003 D1, and the stat tiers follow as ADR-002 delivers them. #1011 ran its stats select inside `/load`, which is why its load took 2.4 s at 78M rows; D8 moves that out of the load.

### D3. An unfiltered, unsorted window is a slice

`lf.slice(start, n).with_row_index(offset=start)` collected with the streaming engine: 20 ms and 0.08 GB at 12M, 5 to 16 ms at 78M. The window is clamped as `clamp_window` does today.

### D4. Sorted windows are a key phase and a gather phase

The key phase runs over `with_row_index("i").select("i", sort_col)` only, sorted by `(sort_col, "i")` so ties break by file position and a window is the same on every request (#995).

- When `end <= K` it is `top_k`: 20 to 30 ms and 0.26 to 0.46 GB at 12M, measured at k=200 only. `K` is a constant (open decision 2).
- When `end > K` it is a full key sort, 0.6 s and 1.2 GB at 12M with a string key, and its result, the order array of row indices, is cached (D6).

The gather phase reads the rows named by the window's 100 indices, and only those. A filter by `is_in` over the whole scan is not acceptable (7.52 GB). The two measured shapes are one slice collect per row (0.34 GB, 1.24 s per 100 rows at random positions) and a pyarrow `read_row_group` per touched row group, which was not measured. Where the sort key correlates with file order the indices cluster and consecutive runs could collapse into one slice each, so 1.24 s may be a worst case. That case was not measured.

### D5. Search is a filter over the scan, with the window and the count separated

Search is applied as today (a literal substring over all String columns, #838), as a filter node on the scan. Its cost is the number of String columns times the rows scanned: 0.29 to 0.48 s and 5 to 8 GB at 12M for 29 columns, and 10 to 18 s per request at 78M. Three levers, in the order recommended:

1. **Return the window as soon as it is full and deliver the count later.** At 12M rows the first 100 matches took 0.29 s against 0.41 s for the count, at the same 5 GB, so the gain measured there is small; the split at 78M, where a request cost 10 to 18 s, was not measured. The total comes from a count pass the server runs afterwards in row-group chunks and pushes with ADR-002's `stats_update` channel. This needs a client change, because `infinite_resp.length` is required today and the grid needs a length to size its scrollbar. The grid can use the unfiltered row count as an upper bound until the count arrives.
2. **Cache the result of a term.** The matching row indices for a term, capped in size, turn paging through a search into a gather. Without it, the 78M run paid 10 to 12 s again for window 5000:5100 after window 0:100 of the same term.
3. **Chunk the scan** (1M-row chunks: 2x lower memory, 2 to 4x the time). It is a fallback if levers 1 and 2 are not accepted, not a bound.

Search restricted to one column was 0.06 s and 0.58 GB. Whether the product searches a chosen subset of columns instead of all of them is open decision 4.

### D6. Order arrays and match lists are cached on disk, keyed by file identity

A full key sort (D4) and a match list (D5) are expensive to make and small to keep: 4 bytes per row, 312 MB for 78M rows when every row matches, so they are written to a file in a cache directory and read back with `np.memmap`. The key is `(path, size, mtime_ns, filter term or None, column, direction)`, so a changed file misses. Entries are evicted least-recently-used under a byte cap. ADR-001's stat cache does not apply: it keys per-cell stats, and these arrays have a different shape and lifetime.

### D7. Memory is a tested property

The 78M run's RSS rose over three rounds and the cause is not identified (allocator retention, a polars-internal cache and a leak all fit). So the backend ships with a test that replays a fixed mix of windows, sorts and searches against a generated file of about 5M rows and fails if RSS at the end of round N exceeds RSS at the end of round 2 by more than a fixed margin. The margin is set once the experiment under open decision 6 has run, and the test is marked slow if it does not fit the suite's time budget. The server is synchronous, so one request is in flight at a time and the bound is the largest single request plus what sessions retain.

### D8. Stats come from ADR-003, executed as a lazy select

The scan backend adds a lazy executor and no policy of its own. Footer values (`length`, `null_count`, exact integer `min` and `max`) first, then the scalar tier as one streaming `select` over the scan, in column chunks when the table is wide (xorq's column chunks halved peak RSS at the same total time on parquet; polars is not measured). The 78M figures above show the `full` tier cannot run on a scan unchunked: 18.3 GB for the quantile and histogram keys. `StatsLimits` gets a `polars-scan` backend row, and ADR-003's `scalar` and `approx` budgets apply to it. Keys that need a per-column `value_counts` over the whole table (`value_counts`, `memory_usage`) are omitted and listed in `omitted_keys`, as #1011 did.

### D9. What a scan session does not offer

Autocleaning and post-processing (#1011 did not offer them on lazy sessions), CSV and ndjson sources, multi-file and hive-partitioned datasets, and writes. A session that asks for one gets the eager path or an error that says why.

## Consequences

- Parquet `/load` memory no longer grows with row count for loading, unsorted windows and top-of-sort windows. Deep sorts and searches grow with the key columns and the number of String columns, within the bounds D7 tests.
- Sort and search answer over the whole file, not over a 1M-row sample (#992). Results for a file above 1M rows change; there is no flag to restore the sample.
- Sorting a deep window of a string key costs about 0.6 s the first time per column and direction at 12M rows (D4), and a gather costs up to about 1.2 s per window at random positions. Both are slower than today's 70 to 105 ms over the sample.
- Search over all String columns remains the expensive request. D5 changes when the user waits for it, not what it reads.
- This resolves #992 and #993 for parquet, and #995 through D4's tie-break. #1011 is not reopened; D1, D3, D4's key phase and D8 reuse its structure.

## Alternatives considered

- **Keep eager polars and optimize it** (#1000, #1005, closed). 0.543 GB per Mrow puts 78M at about 42.6 GB, and a sorted window with `pre_limit=False` peaks at 3.0x the frame.
- **Route large polars entries to xorq.** xorq windows on a 10.8M-row parquet entry take 15 to 26 ms, sorts 210 to 384 ms and searches 504 to 1063 ms, so it works, but it needs a catalog entry and a second backend where a plain parquet path should do. The maintainer chose `scan_parquet` as the destination.
- **Ship #1011 as it was.** Its sorted and searched windows cost 10 to 23 s at 78M and its RSS had not levelled off.
- **Sort the whole frame lazily and rely on polars' optimizer.** On polars 1.35.2, `sort` plus `slice` over the whole frame peaked at 10.5 to 14.6 GB in the measured runs.
- **A time-sliced scan on the IOLoop.** The server stays synchronous and defers work with `IOLoop.add_callback`. Chunked scans in D5 yield between chunks that way. Threads and `async def` are not used.

## Open decisions

1. **Default.** A parquet `/load` on the polars backend is a scan session by default with `polars_mode: "eager"` as an escape hatch for one release (recommended), or opt-in.
2. **`K` for top-k.** Only k=200 is measured. Measure k=1,000 and k=10,000 over a key-only scan before choosing; past `K` the cached order array takes over.
3. **Order-array cache.** Disk with a byte cap (recommended, D6), memory only, or none with a full key sort per request (0.6 s at 12M, about 4 s at 78M by linear extrapolation).
4. **Search scope.** All String columns as today (recommended, with D5's lever 1), or a user-chosen subset, which is cheap but changes behavior.
5. **Gather.** One polars slice per run of consecutive indices (recommended to start), or pyarrow row-group reads. Needs a measurement at 78M with a string sort key.
6. **The RSS drift.** Run the 78M request mix twice, in one process and with each request in a fresh subprocess, and compare end-of-run RSS. This sets D7's margin and shows whether a process boundary is needed.
7. **Chunk size for stats and search on a scan.** 262,144 rows (one row group) or 1M. Needs the 78M run.
8. **Multi-file and hive datasets.** Out of this ADR (D9); decide whether a later one covers them or they go through xorq.

## Not decided here

- **Stat tiers and the policy table** (ADR-003) and **when stats reach the client** (ADR-002). D8 and D5 depend on both.
- **Per-column projection of windows to the visible columns.** It would cut gather and window cost and is a client protocol change.
- **CSV and ndjson sources.**
