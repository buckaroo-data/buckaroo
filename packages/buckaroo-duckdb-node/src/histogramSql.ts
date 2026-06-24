/**
 * Histogram SQL: turn a renamed relation + column alias into the small
 * aggregate queries that feed `histogram.ts`.
 *
 * Two shapes, mirroring the two Python paths:
 *   - NUMERIC — `quantile_cont(col, 0.01/0.99)` for the tails, then the meat
 *     (values strictly between the tails) bucketed into 10 `width_bucket` bins.
 *     This is the DuckDB equivalent of `np.histogram(meat, 10)` over the
 *     1st–99th percentile range (pd_stats_v2.py:histogram_series).
 *   - CATEGORICAL — top-7 value counts plus the `unique`/`longtail` aggregates.
 *
 * The numeric meta the dispatcher needs (is_numeric, distinct_count, min, max,
 * null %) already comes from `SUMMARIZE` (stats.ts), so a numeric column costs
 * one extra query and a categorical column one — no per-column count pass.
 */

import { quoteIdent } from './rename.js';
import { duckTypeToColType } from './duckTypes.js';
import {
  buildHistogram,
  type CategoricalArgs,
  type NumericHistogramArgs,
  type ValueCount,
} from './histogram.js';
import type { DuckSource, SDType } from './DuckSource.js';
import type { RenamePlan } from './rename.js';
import type { HistogramBar } from './wireTypes.js';

/** Number of meat buckets, matching `np.histogram(meat, 10)`. */
export const MEAT_BINS = 10;

/**
 * Numeric histogram query: the 1st/99th percentile tails and the meat bucketed
 * into 10 equal-width bins. Returns up to 10 rows `{low_tail, high_tail,
 * meat_min, meat_max, bin, c}` (bin is 0-based; the tail/min/max columns repeat
 * per row). Zero rows means a degenerate meat range (all meat values equal) —
 * the caller falls back to the categorical histogram.
 *
 * The bin is `floor((v - meat_min) / width)` clamped to `[0, 9]` — DuckDB has
 * no `width_bucket`, and this matches `np.histogram(meat, 10)`'s
 * left-closed/last-inclusive edges (the meat_max value floors to 10 and is
 * clamped back into the final bin).
 */
export function numericHistogramSql(relation: string, alias: string): string {
  const col = quoteIdent(alias);
  const lastBin = MEAT_BINS - 1;
  return `WITH _src AS (${relation}),
_q AS (
  SELECT quantile_cont(${col}, 0.01) AS low_tail,
         quantile_cont(${col}, 0.99) AS high_tail
  FROM _src
),
_meat AS (
  SELECT CAST(${col} AS DOUBLE) AS v
  FROM _src, _q
  WHERE ${col} > _q.low_tail AND ${col} < _q.high_tail
),
_mm AS (SELECT min(v) AS meat_min, max(v) AS meat_max FROM _meat)
SELECT
  (SELECT low_tail FROM _q) AS low_tail,
  (SELECT high_tail FROM _q) AS high_tail,
  _mm.meat_min AS meat_min,
  _mm.meat_max AS meat_max,
  least(${lastBin}, greatest(0, floor((_meat.v - _mm.meat_min) / ((_mm.meat_max - _mm.meat_min) / ${MEAT_BINS}.0))))::INTEGER AS bin,
  count(*) AS c
FROM _meat, _mm
WHERE _mm.meat_max > _mm.meat_min
GROUP BY ALL
ORDER BY bin`;
}

/**
 * Categorical value-counts query: the top-N distinct values by frequency, each
 * row carrying the column-wide `non_null` and `unique_count` aggregates so the
 * caller can derive the longtail without a second pass. Zero rows means an
 * all-null column.
 */
export function categoricalHistogramSql(relation: string, alias: string, topN = 7): string {
  const col = quoteIdent(alias);
  return `WITH _src AS (${relation}),
_vc AS (
  SELECT ${col} AS val, count(*) AS c
  FROM _src
  WHERE ${col} IS NOT NULL
  GROUP BY ${col}
),
_agg AS (
  SELECT
    coalesce(sum(c), 0) AS non_null,
    coalesce(count(*) FILTER (WHERE c = 1), 0) AS unique_count
  FROM _vc
)
SELECT
  CAST(_vc.val AS VARCHAR) AS name,
  _vc.c AS c,
  _agg.non_null AS non_null,
  _agg.unique_count AS unique_count
FROM _vc, _agg
ORDER BY _vc.c DESC, name
LIMIT ${topN}`;
}

function num(v: unknown): number {
  if (v === null || v === undefined) return NaN;
  return typeof v === 'bigint' ? Number(v) : Number(v as number);
}

/** Build `NumericHistogramArgs` from the numeric query rows, or null if degenerate. */
export function parseNumericArgs(rows: Array<Record<string, unknown>>): NumericHistogramArgs | null {
  if (rows.length === 0) return null;
  const first = rows[0];
  const meatMin = num(first.meat_min);
  const meatMax = num(first.meat_max);
  if (!Number.isFinite(meatMin) || !Number.isFinite(meatMax) || meatMax <= meatMin) {
    return null;
  }
  const meatCounts = new Array<number>(MEAT_BINS).fill(0);
  for (const r of rows) {
    const bin = num(r.bin);
    const c = num(r.c);
    if (bin >= 0 && bin < MEAT_BINS) meatCounts[bin] = c;
  }
  const width = (meatMax - meatMin) / MEAT_BINS;
  const endpoints = Array.from({ length: MEAT_BINS + 1 }, (_, i) => meatMin + i * width);
  return {
    meatCounts,
    endpoints,
    lowTail: num(first.low_tail),
    highTail: num(first.high_tail),
  };
}

/** Parse the categorical query rows into `categoricalHistogram` inputs. */
export function parseCategorical(rows: Array<Record<string, unknown>>): CategoricalArgs {
  if (rows.length === 0) return { top: [], restSum: 0, uniqueCount: 0 };
  const nonNull = num(rows[0].non_null);
  const uniqueCount = num(rows[0].unique_count);
  const top: ValueCount[] = rows.map((r) => ({ name: String(r.name), count: num(r.c) }));
  const topSum = top.reduce((a, b) => a + b.count, 0);
  return { top, restSum: Math.max(0, nonNull - topSum), uniqueCount };
}

/** Per-column metadata the dispatcher needs, derived from the SUMMARIZE stats. */
interface ColMeta {
  isNumeric: boolean;
  distinctCount: number;
  length: number;
  nanPer: number;
  min: number | null;
  max: number | null;
}

function colMeta(sd: SDType[string] | undefined, duckType: string, length: number): ColMeta {
  const colType = duckTypeToColType(duckType);
  const isNumeric = colType === 'integer' || colType === 'float';
  const nullCount = num(sd?.null_count);
  return {
    isNumeric,
    distinctCount: num(sd?.distinct_count) || 0,
    length,
    nanPer: length > 0 && Number.isFinite(nullCount) ? nullCount / length : 0,
    min: isNumeric && typeof sd?.min === 'number' ? sd.min : null,
    max: isNumeric && typeof sd?.max === 'number' ? sd.max : null,
  };
}

function computeColumnHistogram(
  source: DuckSource,
  relation: string,
  alias: string,
  meta: ColMeta,
): Promise<HistogramBar[]> {
  // The numeric-vs-categorical dispatch lives in histogram.ts:buildHistogram
  // (the single, unit-tested copy). Here we only supply the lazy SQL fetchers,
  // so the categorical query runs only when the numeric path doesn't win.
  return buildHistogram({
    ...meta,
    fetchNumericArgs: async () =>
      parseNumericArgs(await source.queryRows(numericHistogramSql(relation, alias))),
    fetchCategorical: async () =>
      parseCategorical(await source.queryRows(categoricalHistogramSql(relation, alias))),
  });
}

/**
 * Compute the `histogram` bar list for every column of the renamed relation,
 * keyed by alias. A failure on any single column yields an empty histogram for
 * that column rather than failing the whole `initial_state`.
 */
export async function computeHistograms(
  source: DuckSource,
  relation: string,
  plan: RenamePlan,
  sd: SDType,
  length: number,
): Promise<Record<string, HistogramBar[]>> {
  const out: Record<string, HistogramBar[]> = {};
  for (const c of plan.columns) {
    const meta = colMeta(sd[c.alias], c.type, length);
    try {
      out[c.alias] = await computeColumnHistogram(source, relation, c.alias, meta);
    } catch {
      out[c.alias] = [];
    }
  }
  return out;
}
