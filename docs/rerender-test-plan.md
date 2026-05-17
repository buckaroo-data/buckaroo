# Re-render & Flash Test Plan

## Goal

Comprehensive automated tests that capture, for every kind of state change, exactly what AG-Grid does today: does it remount, does it refetch, does it just refresh cells, or does it do nothing? These tests serve three purposes:

1. **Document the design** — the matrix below is the spec for "when is a full reset *necessary* vs when is it gratuitous (a flash)."
2. **Pin current behavior** so the SPA `dataframe_id` refactor and the #719 view-layer wiring don't regress anything.
3. **Make the refactor mechanical** — each fix flips one test from "asserts current behavior" to "asserts desired behavior."

## Motivating use cases

- **SPA embedding** — host app passes a `dataframe_id`. When it changes the widget should fully reset (new dataset). When it stays the same, no state change should remount AG-Grid.
- **#719 (open PR)** — sort and filter must not invalidate cached rows; only postprocessor / mutate operations get a fresh `RowStore`. Today's `outside_df_params` lumps everything together via the React `key` trick, which conflicts with the future view-layer model.

## What we measure

The existing AG-Grid mock in `DFViewerInfinite.test.tsx` captures props. Extend it (in a new `test-utils/agGridSpy.ts`) to also capture:

| Signal | Why it matters |
|---|---|
| Mount count | Catches `key={…}` remounts — the main flash cause |
| `getRows` calls | Datasource churn; sourceName tells us cache namespacing |
| `setGridOption(...)` calls | Soft-update path (`pinnedTopRowData`, `rowData`, `datasource`) |
| `refreshCells` / `purgeInfiniteCache` / `refreshInfiniteCache` | Invalidation paths the refactor will introduce |
| Column def identity churn | Did the column structure actually change, or just lose memo? |
| `getRowId` outputs per index | Row ID stability across renders (today it's salted with outside params) |

Each test calls `createAgGridSpy()` → gets a `{ mock, calls }` pair → asserts on `calls`.

## State-change matrix

Legend: **R** = full remount, **D** = datasource swap (no remount), **P** = `purgeInfiniteCache`, **S** = `setGridOption`, **C** = `refreshCells`, **·** = no grid touch.

| Trigger | Today (main) | Desired post-refactor | Desired post-#719 |
|---|---|---|---|
| `dataframe_id` (SPA, new) | n/a | D + P + scroll-to-top | same |
| `post_processing` change | **R** | D + P | D + P (new RowStore) |
| `operations` change | **R** | D + P | D + P (new RowStore) |
| `cleaning_method` change | D (via `mainDs` deps; no key change but new ds identity → flash) | D + P | D + P |
| `quick_command_args` (mutating) | **R** | D + P | D + P |
| `quick_command_args.search` (filter-like) | **R** | D + P | **·** + view swap (FilterView) |
| Sort change | getRows with new sortModel (refetch block) | same | **·** + view swap (SortView) |
| `activeCol` change | C (correct already) | same | same |
| `df_display` main ↔ summary | **R** + data_type Raw↔DataSource swap | structural — see open question | same |
| `summary_stats_data` update | S (`pinnedTopRowData`) | same | same |
| `df_viewer_config.column_config` reshape | column defs new identity; no row refetch | same | same |
| `df_viewer_config` style-only tweak | column defs new identity (over-invalidation) | minimal cell refresh | same |
| `df_meta.total_rows` change | propagates via wrapper.length | row count update only | same |
| `show_commands` toggle | sibling DOM + `buckaroo_state` ref change ripples into `mainDs`/`data_wrapper` deps | **·** | **·** |
| Theme / OS scheme | rebuilds `myTheme` memo | same (no regression) | same |
| In-flight response after newer change | namespaced by sourceName in cache, should drop | same | same |
| `outsideDFParams` identity-only churn (same values, new array literal) | downstream `useMemo` thrash | stable identity | stable identity |

## Tests to write today (current-main behavior)

These go in two files. Each test asserts the **current** behavior; tests that capture the flash are clearly named so we know they're tracking pain, not validating it.

### `DFViewerInfinite.flash.test.tsx` (leaf component)

1. `post_processing change remounts AG-Grid` — mount count 1→2. Captures the current `key`-based flash.
2. `outside_df_params identity-only change does NOT remount` — same value, new array literal; mount stays 1.
3. `activeCol change triggers refreshCells, not remount` — refreshCells called with the two affected columns.
4. `summary_stats_data update calls setGridOption('pinnedTopRowData') without remount`.
5. `Raw data update calls setGridOption('rowData') without remount` (tighten existing).
6. `Sort change calls getRows with new sortModel` — datasource exercised, mount stays 1. Sort-refetch is today's behavior; will flip post-#719.
7. `getRowId for the same index changes when outside_df_params change` — captures the row-id-salting behavior that defeats row recycling.
8. `Theme / colorScheme change does NOT remount or refetch`.
9. `column_config reshape rebuilds column defs but does not call getRows`.

### `BuckarooInfiniteWidget.flash.test.tsx` (integration — new file)

10. `show_commands toggle does NOT touch the grid datasource` — likely **fails today** because `buckaroo_state` ref change ripples through `data_wrapper`/`mainDs` deps. This is the test that exposes the memo-dep widening problem.
11. `cleaning_method change rebuilds datasource` — current behavior (flashes via new ds identity, not via React key).
12. `outsideDFParams reference stable when no relevant state changed` — likely **fails today** (it's a fresh array literal every render). Drives the `useMemo` fix.
13. `df_display switch (main → summary) swaps data_type Raw↔DataSource` — captures the legitimate-reset path.

### Edge cases / races

14. `Stale infinite_resp from a previous outside_df_params is discarded` — fire getRows under sourceName=A, change params to B, deliver A's response late, assert no stale rows applied. Likely already handled by `KeyAwareSmartRowCache`'s sourceName namespacing — but un-tested.
15. `Summary stats update during in-flight getRows applies pinned rows without cancelling the fetch`.
16. `activeCol persists across a post_processing change` — today the prop survives but the AG-Grid `context` is reset by the remount; documents the UX cost.

## DOM verification (Playwright)

The jest matrix above stops at the AG-Grid API contract — "did `setGridOption('rowData', X)` get called" — because AG-Grid itself is mocked. That catches missed plumbing but not the case where we call the right methods and AG-Grid silently keeps showing stale rows. For each row in the matrix that has a user-visible value swap, we need one Playwright assertion that the new values are actually in the DOM.

Infrastructure already in place: `playwright.config.ts` points at Storybook on :6006, `pw-tests/ag-pw-utils.ts` has `waitForCells`, and the relevant stories already exist. New file: `pw-tests/rerender.spec.ts`.

### Cases to cover

| Case | Story to target | Assertion |
|---|---|---|
| `outside_df_params` swap shows new dataset values | `OutsideParamsInconsistency--primary` (already has Toggle button) | Click "Toggle Params"; assert cells contain `B1/B2/B3`, not `A1/A2/A3`. Toggle back; assert `A1` returns. |
| `outside_df_params` swap with network delay (no stale-after-toggle race) | `OutsideParamsInconsistency--with-delay` | Toggle, wait for `B1`; assert no `A*` value is ever visible after the toggle settles. |
| Pinned-row update reflects in DOM without flicker | `PinnedRowsDynamic` | Trigger the dynamic update; assert pinned-row cell text changed to the new value. |
| Pinned-row race (rapid updates) | `PinnedRowsRace` | After all updates settle, assert the final value is visible (no torn state). |
| `post_processing` change via BuckarooWidgetTest | `BuckarooWidgetTest` (add a postprocessing toggle if not present) | Change postprocessing; assert at least one cell value changed to the postprocessed result. |
| Sort change shows reordered rows | any infinite-row story | Click a column header; assert row at index 0 now has the highest/lowest value for that column. |
| Column reshape shows new column header in DOM | `Styling` or similar | Change `column_config`; assert new header text is in DOM, old header is gone. |
| `dataframe_id` reset (deferred — write when prop lands) | new story `DataframeIdReset` | Set initial dataset, scroll down, change `dataframe_id`; assert new dataset values appear at top, scroll returned to 0. |

### How this overlaps with jest

The jest matrix and Playwright suite are complementary, not redundant:

- **Jest** asserts the *mechanism* — mount count, getRows arguments, setGridOption calls. Runs in seconds; gates every commit.
- **Playwright** asserts the *outcome* — cell text in the DOM. Slower, but catches AG-Grid behavior the mock can't model (virtualization, cell renderers, refresh timing).

If a future change calls all the right APIs but the cell still shows stale text, only Playwright catches it. If a change accidentally adds an extra mount but the cell text is still right, only jest catches it. Both are needed.

### Convention for "current behavior" Playwright cases

Same as Option A in jest: the Playwright tests assert what users see **today** with the `key`-driven remount in place. If a cell flashes empty then fills in, the assertion is "after settle, B1 is visible" — not "during the swap, no empty state is shown." We'll add the flash-free assertions in the refactor PR when the implementation can satisfy them.

## Tests deferred (documented in matrix, not written until refactor)

- `dataframe_id` change → full reset path (write when the prop lands)
- Sort change → no `getRows` call (write when #719's view layer is wired)
- Filter / search change → no `getRows` call (write when #719's view layer is wired)

## Refactor sequence enabled by this suite

Once the suite is green on main:

1. Memoize `outsideDFParams` in `BuckarooInfiniteWidget` → flips test 12.
2. Narrow `data_wrapper` / `mainDs` deps to specific fields → flips test 10.
3. Remove `key={JSON.stringify(outside_df_params)}` on `AgGridReact`; add an effect that calls `purgeInfiniteCache()` on a memoized signature → flips test 1.
4. Drop the outside-key suffix from `getRowId` → flips test 7.
5. Introduce `dataframe_id` prop; treat it as the *only* trigger for the full-reset path → add the deferred SPA test.

Each step is a small PR with a clearly named test transition.

## Open design questions (resolve before refactor, not before tests)

1. **`dataframe_id` API shape.** New top-level prop, or one key inside `outside_df_params`? Folding keeps the surface small; separating makes "this is a hard reset" semantically distinct.
2. **`df_display` main ↔ summary.** Currently swaps Raw↔DataSource. Is preserving scroll/column state across this swap valuable, or is it expected to feel like switching panels? If the latter, the remount is fine and we just want it to be the *only* place the remount happens.
3. **Sort-changed scroll behavior.** Today sorts call `ensureIndexVisible(0)`. After #719 the sort is a pure view permutation; do we still scroll to top, or hold the user's position?

## Harness sketch

```ts
// test-utils/agGridSpy.ts
export interface AgGridSpyCalls {
  mountCount: number;
  setGridOption: Array<[string, unknown]>;
  refreshCells: RefreshCellsParams[];
  refreshInfiniteCache: number;
  purgeInfiniteCache: number;
  getRowsCallArgs: IGetRowsParams[];
  rowIdsByIndex: Map<number, Set<string>>; // index → distinct IDs observed
  lastProps: any;
}

export const createAgGridSpy = (): {
  install: () => void;   // wires jest.mock for "ag-grid-react"
  calls: AgGridSpyCalls;
};
```

Tests then look like:

```ts
const { install, calls } = createAgGridSpy();
install();
const { rerender } = render(<DFViewerInfinite ... outside_df_params={{ pp: "a" }} />);
rerender(<DFViewerInfinite ... outside_df_params={{ pp: "b" }} />);
expect(calls.mountCount).toBe(2); // current behavior
// after refactor this becomes: toBe(1) + expect(calls.purgeInfiniteCache).toBe(1);
```

## Running

```
cd packages/buckaroo-js-core && pnpm test            # jest matrix (fast, runs on every commit)
cd packages/buckaroo-js-core && pnpm run test:pw     # Playwright DOM checks (slower, CI-gated)
```

Both layers must be green before the PR merges. The jest matrix locks in the AG-Grid contract; the Playwright suite locks in what the user actually sees.
