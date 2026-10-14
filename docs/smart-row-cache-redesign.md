# SmartRowCache redesign — rowid-keyed store + view permutations

## Status
Phases 1-7a landed (PR #719, merged to `main`); the negative-start `rowidsInRange` bug found while evaluating them was fixed in #942. Design decisions for the consumer cutover were resolved 2026-06-25 — see [Decisions resolved (2026-06-25)](#decisions-resolved-2026-06-25); they supersede the original "Decisions" set where they conflict. The remaining consumer cutover (phases 7b-7e) is planned in detail at the bottom.

## Decisions resolved (2026-06-25)

Resolving the two blockers found while evaluating phase 1-7a. These supersede the conflicting bullets under "Decisions" below.

### A — `getRowsByRowid([…])` is in v1 (reversed)

After a sort, the visible window maps to an arbitrary, non-contiguous set of rowids. A positional `populate(start, end)` against the *unsorted* tagged expression cannot fetch them, and re-`order_by`-ing the whole expression per window is exactly the cost this redesign removes. The fetch-by-rowid path is the one the JS side already speaks — `missingAt(view, start, end)` returns the missing rowids, and:

```
getRowsByRowid({sourceName, rowids: Int32Array})
  → {rowids: Int32Array, rows: Row[]}
```

fetches exactly those. `populate(start, end)` stays as the cheap path for the default (identity) view and eager head/tail prefetch; `getRowsByRowid` is the general path whenever a non-identity view is active.

### B — every view is an ordered list of `original_row_id`s

The rowid is the **`original_row_id`**: the stable identity of a row in the source frame as delivered, decoupled from display position. `RowStore` is keyed by it, and `SortView`/`FilterView` are already just `Int32Array`s of these ids — so they unify into one ordered-rowid-list view (`IdentityView` stays the privileged no-array case):

- sort → all N ids, reordered
- filter / search → a subset of ids
- **filter + sort → the filtered subset in sort order** — still one ordered id list

Because everything shares the one id namespace, "filtered then sorted" composes for free, client-side, no extra round-trip:

```
combined = sortView.rowidOrder.filter(r => filterSet.has(r))
```

Prefer this client-side intersection (the client already holds the full sort permutation and the filter subset); fall back to a server-composed combined list only when one input is absent. This also resolves the "scrambled filter order" issue: a filter-only view in original order is the subset ascending by `original_row_id`.

### The cache key is the *generation*, not the sort

`KeyAwareSmartRowCache` selects a cache by `${sourceName}-${sort}-${sort_direction}` (`getSourcePayloadKey`), conflating content identity with sort — the root reason a sort refetches everything. The new selection key is the **generation key**: only the ops that *change row content* (postprocessor, low-code mutate), classified by the lisp "changes rows" annotation. Sort and filter come *out* of the key and become views inside one `RowCache`.

`Map<generationKey, RowCache>` replaces `Map<getSourcePayloadKey, SmartRowCache>`; `KeyAwareSmartRowCache`'s outer-map + callback machinery is lifted into the new controller — only the key *definition* changes. `sourceName` (= `JSON.stringify(outside_df_params)`) currently folds filter/search in, so the cutover must split `outside_df_params` along the same annotation: sort + filter/search → views, content-changers → generation key.

`original_row_id` is stable only *within* a generation; a content-changing op re-tags and resets the namespace, invalidating that generation's views and `RowStore`.

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

## Decisions (original set)

> Superseded where noted by [Decisions resolved (2026-06-25)](#decisions-resolved-2026-06-25).

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
| auto-clean (additive columns) | no | v1: generation reset; v2: column delta — see [Forward compatibility](#forward-compatibility) |

The lisp return value carries an annotation flag. Search is the canonical "filter-only" op. Auto-cleaning is row-preserving and additive at the column level, so it is a generation reset in v1 only for simplicity — see [Forward compatibility](#forward-compatibility).

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

A `getRowsByRowid([…])` endpoint **is** in v1 (reversed 2026-06-25 — see [Decisions resolved → A](#decisions-resolved-2026-06-25)). It is the general fetch path once any non-identity view is active.

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
| 7a | RowCache.test.ts: end-to-end controller behavior | `RowCache.ts` |
| 7b | Wire RowCache into `TableInfinite.tsx` consumer | replace KeyAwareSmartRowCache reads |
| 7c | Wire `row_cache_payloads` into widget message handler | new `populate` / `sort` / `filter` message kinds |
| 7d | Verify Playwright tests pass with new wire protocol | update fixtures as needed |
| 7e | Retire `SmartRowCache.test.ts` (keep tests for `KeyAwareSmartRowCache` if it survives as the "rows that change" path) | net deletion |

Phases 1-5 are pure TS, no Python touched. Phase 6 is the Python contract. Phase 7a is the JS controller layer (the API consumers will use). Phases 7b-e are the actual consumer cutover and are the next session of work.

## What's built

| File | Surface |
|---|---|
| `packages/buckaroo-js-core/src/components/DFViewerParts/RowStore.ts` | `set/setMany/get/getMany/has/delete/size/rowids/missingRowids` |
| `…/Views.ts` | `View` interface + `IdentityView` / `SortView` / `FilterView` |
| `…/RowStoreGc.ts` | `gcRowStore(rs, activeWindows, padding, pin?)` |
| `…/ViewRegistry.ts` | LRU cache of views keyed by `viewKey()` |
| `…/RowCache.ts` | Integration controller — the API the consumer uses |
| `buckaroo/row_cache_payloads.py` | `tag_with_rowids` + populate/sort/filter response builders |

## Remaining implementation plan (7b-7e)

Phases 1-7a shipped the primitives (`RowStore`, the unified view, GC, registry, `RowCache` controller) and the Python payload builders. None of it is wired to a consumer: `TableInfinite.tsx` is a dead stub (`<h1>broken</h1>`); the live path is `BuckarooWidgetInfinite.tsx::getKeySmartRowCache` → `getDs` (`gridUtils.ts`) → `KeyAwareSmartRowCache`, and Python dispatches `infinite_request` → `_handle_payload_args` (three near-duplicate copies: `buckaroo_widget.py`, `polars_buckaroo.py`, `xorq_buckaroo.py`) via `payload_bridge`.

### API-surface gaps in 1-7a the consumer needs first

`RowCache` is pure state. Before any wiring it needs:

1. **Request/callback orchestration.** "fire request, park callback, replay on response, dedupe in-flight, eager head/tail prefetch" — all of which `KeyAwareSmartRowCache.getRequestRows`/`addPayloadResponse` provide today and `RowCache` does not. This is the bulk of 7b. Lift it from `KeyAwareSmartRowCache` into a `RowCacheController`.
2. **Eager head/tail helper.** GC *pins* head/tail; the controller must compute the `[0, head)` / `[N-tail, N)` windows to fetch after a sort lands. Add `RowCache.headTailWindowsToFetch(view)`.
3. **`getRowsByRowid` plumbing** (decision A) — JS request trigger + Python builder.
4. **pandas/polars tagger.** `tag_with_rowids` is xorq-only (`to_pyarrow()` + memtable). The pandas/polars handlers need a parallel int32 `_buckaroo_rowid` appender before they can serve any payload.

### 7b — Wire RowCache into the datasource (JS)

New `gridUtils.ts::getRowCacheDs()` (parallel to `getDs`); `BuckarooWidgetInfinite.tsx` builds a `RowCacheController` (the `Map<generationKey, RowCache>` + callback bookkeeping lifted from `KeyAwareSmartRowCache`); `getRowId` switches from `data.index` to `data._buckaroo_rowid`. The datasource translates AG-Grid's positional `getRows(start, end, sortModel)` into:

1. Resolve the active view — no sortModel → `defaultView()`; sortModel → `getSortView(col, dir)`, and if absent, fire a `sort` request and park the callback until `rowidOrder` lands (the view doesn't exist until the permutation arrives — the central new async step). Compose an active filter by client-side intersection (decision B).
2. `missingAt(view, start, end)` → if empty, `successCallback(rowsAt(...), view.length())` + `gc(...)`. If non-empty, fetch the missing rowids via `getRowsByRowid` (or positional `populate` for the identity view), park the callback, replay on response.

**Biggest risk:** sort is now two round-trips before a visible row (sort → `rowidOrder` → fetch rows), where today it's one. AG-Grid has no "permutation loading" state. The controller must guarantee exactly one callback resolution per `getRows` across the chain and dedupe an in-flight `sort` for the same view, or it deadlocks / double-fetches.

### 7c — Wire row_cache_payloads into the Python handler

Extend `payload_bridge` to route `msg.type ∈ {populate, sort, filter, getRowsByRowid}` to new handlers, leaving the legacy `infinite_request` path intact during cutover. `tag_with_rowids` runs **once at widget init** (rowids stable for the session) and re-tags only on a generation change. Build the pandas/polars tagger first (TDD, mirror `test_row_cache_payloads.py`).

**Total-order invariant (most important correctness rule):** append `_buckaroo_rowid` as the final `order_by` tiebreaker in *both* `make_sort_payload` and any populate-under-sort path. `order_by` on a non-unique column has nondeterministic tie order across executions; if the sort's order and a fetch's order disagree, the grid shows wrong rows with no error. Decision A (fetch by rowid, not by position-in-sort) removes most of this exposure, but keep the tiebreaker.

### 7d — Playwright / fixtures

The Storybook story fakes (`SmallDFScroll`, `BuckarooWidgetTest`, `FitContentHeight`) instantiate `KeyAwareSmartRowCache` + `getDs` directly and reply via `setTimeout`; rewrite them to speak the new message kinds. Keep one story on the old path while `KeyAwareSmartRowCache` survives. The two-round-trip sort means any "click sort → assert content immediately" test must wait on the row fetch, not just the sort.

### 7e — Delete dead code

`KeyAwareSmartRowCache`'s per-generation map + callback machinery survives (lifted into the controller); only `SmartRowCache`'s segment algebra and `SmartRowCache.test.ts` retire, plus the `TableInfinite.tsx` stub. Do it as a pure-deletion commit after 7d is green; keep the legacy `infinite_request` path until then for A/B at any commit. Keep `PayloadArgs`/`PayloadResponse`/`getPayloadKey` until every importer is moved.

## Forward compatibility

The redesign decouples row *identity* (`original_row_id`) from row *display position*. The same move applies later to the column axis; v1 must not foreclose it.

**Auto-cleaning is a deliberate v1 generation reset, but is row-preserving and additive.** Changing `dates_as_strings` yields a parsed `dates_as_strings` plus a renamed `dates_as_strings_original` — the original values are untouched, just relabeled, and the parsed values arrive as a new column. So a future optimization can treat cleaning as a **column delta on the same generation** rather than a reset:

- additive clean → keep the `RowStore`, fetch only the new columns (a column-projected `populate`)
- a future row-dropping clean ("remove these outliers") → a `FilterView` (subset) over the same generation

For v1, cleaning stays a generation reset — simple, correct, and cleaning-at-load has no warm cache to preserve. The payoff of the column-delta path is the `cleaning_method` *toggle* on an already-scrolled grid.

**The v2 hook is `original_col_id`** — the column-axis mirror of `original_row_id`: a stable per-column id assigned at first tag and carried through cleaning (the renamed original keeps its id; the new column gets a fresh one). The cell cache then keys on `(original_row_id, original_col_id)`, and the internal a,b,c names, display names, and the `_original` suffix become pure presentation. The internal a,b,c is **positional** today — the column-axis analog of display position — so it must never become a persistent cache key.

**Two guardrails keep the door open at ~zero v1 cost:**

1. Route every op through the single "changes rows / reorder / subset / changes columns" classifier — even though cleaning maps to "reset" in v1 — so it can be reclassified to "column delta" later in one place.
2. Never bake the positional a,b,c (or any display position) into a persistent cache key, on either axis.

**The one v1 simplification v2 revisits:** `RowStore` is row-granular — `has(rowid)` / `missingAt` assume "rowid present ⇒ all columns present". A column-delta clean breaks that. Refining to `(rowid, colid)` granularity is additive and localized (`RowStore.has`/`missingAt` + the datasource fetch loop), not a teardown.

## Out of scope for v1

- Datasets >10M rows — hard cap on whole-dataset permutations. If we want to go bigger, we revisit windowed permutations.
- Column-delta cleaning / `original_col_id` — see [Forward compatibility](#forward-compatibility).
- Multi-sort (sort by A then B). Single sort key only, matching today's behavior.
- Persisting RowStore across widget re-renders. Each widget instance starts fresh.
