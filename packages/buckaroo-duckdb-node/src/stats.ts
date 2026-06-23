/**
 * Summary stats: `SUMMARIZE` → `SDType` → the pivoted stat rows the viewer
 * consumes.
 *
 * The plan's v1 SUMMARIZE → stat mapping:
 *   dtype          ← column_type
 *   min / max      ← min / max
 *   distinct_count ← approx_unique
 *   mean / std     ← avg / std
 *   null_count     ← count × null_percentage (derived)
 *   q25/q50/q75    ← q25 / q50 / q75 (approx)
 *
 * Histograms/quantile displayers are a fast-follow (not in SUMMARIZE).
 *
 * Note on serialization: these are computed aggregate scalars, not user row
 * data, so the no-coercion rule (which exists to protect BigInt/DECIMAL/etc.
 * fidelity on the *row* path) does not apply here. We emit the stats as already
 * pivoted rows over the `json` envelope, so the payload never touches the
 * fragile binary path. If wide-`{col}__{stat}` parquet is later preferred,
 * `sdTypeToWideRow` produces that shape for a `copyToParquet`/`layout:'wide'`
 * round-trip without changing the SDType producer.
 */

import type { SummarizeRow, SDType, SDVal } from './DuckSource';
import { INDEX_COL } from './rename';
import type { DFData, DFDataRow } from './wireTypes';

/** Stat names produced in v1, in the order they should appear as pinned rows. */
export const V1_STAT_NAMES = [
  'dtype',
  'null_count',
  'distinct_count',
  'mean',
  'std',
  'min',
  'q25',
  'q50',
  'q75',
  'max',
] as const;

/** Number if `v` is a finite numeric string/number, else the value unchanged. */
function maybeNumber(v: string | number | null): SDVal {
  if (v === null || v === undefined) return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const trimmed = v.trim();
  if (trimmed === '') return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : v;
}

/** count × null_percentage (a 0–100 percentage) → integer null count. */
function deriveNullCount(
  count: number | string | null,
  nullPct: number | string | null,
): SDVal {
  const c = typeof count === 'string' ? Number(count) : count;
  const p = typeof nullPct === 'string' ? Number(nullPct) : nullPct;
  if (c === null || p === null || !Number.isFinite(c) || !Number.isFinite(p)) {
    return null;
  }
  return Math.round((c * p) / 100);
}

/**
 * Map `SUMMARIZE` rows → `SDType` (keyed by the column name as SUMMARIZE
 * reports it — the alias, when summarizing the renamed relation). The
 * synthesized `index` column is skipped.
 */
export function summarizeToSDType(rows: SummarizeRow[]): SDType {
  const sd: SDType = {};
  for (const r of rows) {
    if (r.column_name === INDEX_COL) continue;
    sd[r.column_name] = {
      dtype: r.column_type,
      null_count: deriveNullCount(r.count, r.null_percentage),
      distinct_count: maybeNumber(r.approx_unique as string | number | null),
      mean: maybeNumber(r.avg),
      std: maybeNumber(r.std),
      min: maybeNumber(r.min),
      q25: maybeNumber(r.q25),
      q50: maybeNumber(r.q50),
      q75: maybeNumber(r.q75),
      max: maybeNumber(r.max),
    };
  }
  return sd;
}

/**
 * Pivot `SDType` into the row-per-stat form the viewer consumes directly:
 * `[{index:'dtype', level_0:'dtype', a:'BIGINT', b:'VARCHAR'}, …]`.
 * Mirrors serialization_utils.py:_pivot_wide_sd_row.
 */
export function sdTypeToStatRows(sd: SDType): DFData {
  const cols = Object.keys(sd);
  return V1_STAT_NAMES.map((stat) => {
    const row: DFDataRow = { [INDEX_COL]: stat, level_0: stat };
    for (const col of cols) {
      row[col] = (sd[col]?.[stat] ?? null) as DFDataRow[string];
    }
    return row;
  });
}

/**
 * Build the single wide `{col}__{stat}` record (serialization_utils.py:
 * sd_to_parquet_b64 naming). List/dict values are JSON-encoded the same way the
 * Python producer does. Provided for a future `layout:'wide'` parquet path.
 */
export function sdTypeToWideRow(sd: SDType): Record<string, SDVal> {
  const wide: Record<string, SDVal> = {};
  for (const [col, stats] of Object.entries(sd)) {
    for (const [stat, val] of Object.entries(stats)) {
      wide[`${col}__${stat}`] = Array.isArray(val) ? JSON.stringify(val) : val;
    }
  }
  return wide;
}
