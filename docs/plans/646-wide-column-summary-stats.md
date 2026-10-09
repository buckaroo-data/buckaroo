# Plan: Replace JSON-in-Parquet summary stats with wide-column layout (#646)

## Context

Summary stats serialization (`sd_to_parquet_b64`) JSON-encodes every cell value to a string before writing to parquet, then JS `JSON.parse`'s every cell back. This defeats parquet's type preservation — numbers, bools, and strings all become JSON strings stuffed in string columns. The fix: flatten to one parquet column per cell (`a__mean`, `a__histogram`, etc.) so scalars go through parquet natively, and only lists/dicts still need JSON encoding.

## Approach

Replace `sd_to_parquet_b64` in-place — no legacy code, no backwards compat format tag. Python flattens the stats dict to `{col__stat: [value]}` (single-row, many columns). JS decodes parquet, pivots the wide row back to the row-based `DFData` that all consumers already expect. The format tag stays `parquet_b64` (same as before).

## Files to modify

### Python: `buckaroo/serialization_utils.py`
1. Add `_to_python_native(val)` — convert numpy scalars to Python builtins for pyarrow
2. Add `_sd_to_parquet_b64_wide(sd)`:
   - Rename columns to a,b,c via `to_chars()` (reuse existing `old_col_new_col` logic)
   - For each `(col, stats_dict)`, for each `(stat, value)`:
     - Column name = `f"{short_col}__{stat}"`
     - If value is list/dict/tuple → JSON-encode to string
     - If value is numpy scalar → convert to Python native
     - If value is None/NaN → store as `None` (pyarrow handles nulls natively)
     - Otherwise → store as-is
   - Build `pa.table()` directly (single-row, one column per cell)
   - Write parquet, base64 encode
   - Return `{'format': 'parquet_b64_wide', 'data': '...'}`
3. Replace `sd_to_parquet_b64` body with the wide-column implementation (no legacy fallback)

### TypeScript: `packages/buckaroo-js-core/src/components/DFViewerParts/resolveDFData.ts`
1. Replace `parseParquetRow()` with `pivotWideSummaryStats(wideRow)` — splits column names on first `__`, groups by stat name, produces `DFData` rows like `{index: "mean", level_0: "mean", a: 42, b: 33}`
2. For complex values (strings that are JSON arrays/objects), JSON.parse them during pivot
3. Update `resolveDFData()` and `resolveDFDataAsync()` to call `pivotWideSummaryStats` on the single decoded row

### No changes needed in downstream consumers
- `extractSDFT()`, `extractPinnedRows()`, AG-Grid pinned rows, `Styler.tsx` — all receive `DFData` after the pivot, same shape as before
- All Python callers of `sd_to_parquet_b64` — same function signature, same tagged return format

## Tests

### Pre-check: DOM integration test
Before making any changes, verify an existing DOM/integration test checks that summary stat rows (e.g. mean, dtype) appear in the rendered grid. If no such test exists, add one. Run it green before proceeding.

### Python: `tests/unit/test_sd_to_parquet_b64.py`
- Rewrite tests for the new wide format (single-row, `col__stat` columns)
- Scalar values are now native types in parquet (not JSON strings)
- Histogram columns are still JSON strings (complex types)
- None/NaN values are explicit nulls in parquet
- Remove old round-trip tests that assert JSON-encoded cells

### TypeScript: `resolveDFData.test.ts`
- Regenerate `test-fixtures/summary_stats_parquet_b64.json` with new wide format
- Add test for `pivotWideSummaryStats` directly
- Remove old `parseParquetRow` tests
- Verify async decode produces correct DFData shape

## Verification

1. Run DOM integration test green BEFORE changes
2. `pytest tests/unit/test_sd_to_parquet_b64.py -vv`
3. `cd packages/buckaroo-js-core && pnpm test`
4. Run DOM integration test green AFTER changes
5. Full test suite: `pytest -vv tests/unit/ && cd packages && pnpm test`
