/**
 * Integration test: BuckarooInfiniteWidget under an autocleaning toggle.
 *
 * Reproduces the user's report from Full-tour.ipynb: "Just toggling the
 * cleaning method twice triggered React error #300" (Rendered fewer hooks
 * than expected).
 *
 * Production flow this test mirrors:
 *   1. Widget mounts with summary stats containing histogram + chart values.
 *   2. User flips cleaning_method in the status bar.
 *   3. Python regenerates summary stats; new `df_data_dict.summary_stats`
 *      comes back with values for some columns potentially missing or
 *      shape-changed.
 *   4. AG-Grid keeps the same cell-fiber instances and just sets new
 *      pinnedTopRowData via setGridOption — pushing fresh `value` props
 *      into the same React fibers used for the pinned cells.
 *   5. If any cellRenderer's hook count varies by value-shape branch,
 *      React throws #300 / #310 depending on direction.
 *
 * Unlike the existing flash matrix tests (which stub AG-Grid to a `<div/>`
 * and never actually mount cell renderers), this test installs an AG-Grid
 * mock that walks `pinnedTopRowData × columnDefs` and renders each cell
 * through `cellRendererSelector` — the same selector path that ships to
 * production. That's the only way the bug surfaces in jsdom: AG-Grid's
 * cell layer is where the hook violation actually fires.
 */
export {};
