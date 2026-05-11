# SmartRowCache redesign — rowid-keyed store + view permutations

## Status
DRAFT — design locked. Implementation pending. Strategy: build alongside, big-bang replace once tests pass.

## Today's architecture (briefly)

`KeyAwareSmartRowCache` routes requests by `${sourceName}-${sort}-${sort_direction}` to a per-sort `SmartRowCache`. Each `SmartRowCache` stores **full row dicts** indexed by absolute position `[start, end)` *under that sort*. GC trims around the most recent request window, LRU evicts whole sort caches across keys.

Cost:

- Sorting a column = fresh empty cache → re-fetch every visible row from the server.
- N sorts × M rows = N copies of the same row in memory.
- Every cache entry is full row data, even though `sort` is a *reorder* operation.
- No way to ship "preview" first/last N rows when the user clicks sort.

## Two-layer cache

1. **`RowStore`** — only place row contents live. Keyed by stable `rowid`. Has its own GC.
2. **View layer** — per-view permutations / subsets of rowids. Cheap (Int32Array).

Renderer composes:
```
view V at position k  →  rowid r = V.rowidOrder[k]  →  RowStore[r]
```

The existing `KeyAwareSmartRowCache` machinery survives, but only for views that **change row contents** (mutate, group-by, join). Sort and filter share the source RowStore.

## Decisions (all locked)

### What is a rowid
Server-assigned monotonic int from the order of the original DataFrame as delivered to the widget. Stable across the session. Decoupled from any user-visible column (not pandas index, not xorq's `index` column — they may exist as columns in their own right, but they are not rowids).

### Default order
"Unsorted" is the as-delivered order. View-position equals rowid. **No N-int permutation array is allocated** for the default view — it's a privileged identity case. SortViews allocate when a sort is actually selected.

### Permutations are whole-dataset
On sort, server ships the full `rowidOrder` for the new sort (one Int32Array of length N). At 4 bytes/row this is 4MB / 1M rows / 40MB / 10M rows. Soft cap on dataset size at ~10M.

### What "changes the rows"
Boundary baked into the lisp annotation:

| Op | Changes rows | View kind |
|---|---|---|
| sort | no | `SortView` (rowid permutation) |
| filter / search | no | `FilterView` (rowid subset) |
| select (column subset) | no | shares RowStore with masked schema |
| postprocessing func | yes | fresh DerivedRowStore |
| most low-code (lisp) ops | yes | fresh DerivedRowStore |
| low-code op annotated as filter-only | no | `FilterView` |

The lisp return value carries an annotation flag. Search is the canonical "filter-only" op.

### Server contract

One request shape, one response shape:

```
populate({sourceName, viewKey?, start, end})
  → {rowids: Int32Array, rows: Row[]}
```

`viewKey` identifies the active SortView / FilterView (absent = default order). The response always pairs rows with their rowids, so positional fetches inside any view re-hydrate the rowstore.

Sort triggers a separate request:

```
sort({sourceName, sortKey, sortDirection})
  → {rowidOrder: Int32Array}
```

No row payload in the sort response. After it lands, the client does its normal positional fetch for the visible window (and an eager fetch for the head/tail; see GC below) using `populate` against the new viewKey.

Filter triggers:

```
filter({sourceName, filterKey})
  → {rowidSubset: Int32Array}
```

No row payload — the subset is rowids, rows are already in the rowstore (or fetched on demand).

A `getRowsByRowid([…])` endpoint is **not** in v1. Adding it later is cheap if scrolling patterns demand it.

### RowStore GC
Two policies, both active:

1. **Visibility-aware.** Compute the union of `[start-pad, end+pad]` *positions* across all active views. Map each to rowids via the relevant `rowidOrder` (or identity for the default view). Keep that rowid set; drop the rest.
2. **Pinned head/tail.** Always keep rowids for the first 20 + last 20 positions of every active SortView (and the default view). Falls out naturally: after a sort response lands, the client eagerly fetches `[0, 20)` and `[N-20, N)` under the new view, populating those rowids and they survive normal eviction.

No pure LRU. (LRU evicts cells the user just visited — bad fit for scroll patterns where you visit a region once and don't return.)

### View LRU
LRU-4 on `SortView`s. Permutations are cheap (4MB/1M rows × 4 = 16MB worst case); keeping 4 alive means toggling between two columns is always instant. FilterViews follow the same LRU-4 cap.

### Migration
Big-bang replacement once the new code reaches feature parity and tests pass:

1. Build `RowStore`, `SortView`, `FilterView` net-new in `RowStore.ts` / `Views.ts`. No changes to `SmartRowCache.ts`.
2. Mirror the existing `SmartRowCache.test.ts` tests against the new shape (where they apply), plus new tests for sort-without-refetch, head/tail pinning, GC across views, mutate carve-out.
3. Implement Python-side server contract changes (`populate` returns `{rowids, rows}`; `sort` / `filter` separate response shapes).
4. Cut over `BuckarooWidgetInfinite.tsx` consumers.
5. Delete `SmartRowCache.ts` + `KeyAwareSmartRowCache` once the existing test suite is rewritten or retired.

### Where this lands
Off `main`, on `feat/smart-row-cache-redesign`. Not stacked on `feat/xorq-buckaroo-widget`.

## Build order (test-first)

Each phase has its own commit pair (failing test → implementation), per repo TDD rule.

| Phase | Test scope | Implementation |
|---|---|---|
| 1 | RowStore.test.ts: get/set/has, byte-aware GC | `RowStore.ts` |
| 2 | Views.test.ts: SortView, FilterView, identity default view, position→rowid lookup | `Views.ts` |
| 3 | Visibility-aware GC: keep union across views, drop rest | RowStore + Views interaction |
| 4 | Pinned head/tail: eager fetch policy after sort lands | client-side fetch logic |
| 5 | LRU-4 on SortViews/FilterViews | view registry |
| 6 | Server contract: extend `populate` to return `{rowids, rows}`; add `sort` / `filter` shapes | Python `_handle_payload_args` |
| 7 | Cut over `BuckarooWidgetInfinite.tsx` consumers; rewrite/retire `SmartRowCache.test.ts`; delete old types | net deletion |

Phases 1-5 are pure TS, no Python touched. Phase 6 is the contract change. Phase 7 is the big-bang.

## Out of scope for v1

- `getRowsByRowid([…])` — only if scroll patterns prove it necessary.
- Datasets >10M rows — hard cap on whole-dataset permutations. If we want to go bigger, we revisit windowed permutations.
- Multi-sort (sort by A then B). Single sort key only, matching today's behavior.
- Persisting RowStore across widget re-renders. Each widget instance starts fresh.
