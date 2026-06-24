/**
 * Histogram bars: the `histogram` summary stat the viewer renders through the
 * `displayer: 'histogram'` pinned row.
 *
 * This is a faithful TS port of buckaroo's Python producer
 * (`customizations/histogram.py`) so a DuckDB-backed column renders the same
 * bars as the pandas/polars backends:
 *
 *   - NUMERIC: a low-tail marker, 10 "meat" buckets over the 1st–99th
 *     percentile range (population %), a high-tail marker, then an NA bucket.
 *   - CATEGORICAL: the top-7 categories (`cat_pop` %), then `longtail`,
 *     `unique`, and `NA` buckets.
 *
 * All percentages are on the 0–100 scale and rounded with numpy's
 * round-half-to-even (`np.round`) so the labels match the Python output
 * bit-for-bit. The SQL that produces the raw inputs lives in `histogramSql.ts`.
 */

import type { HistogramBar } from './wireTypes.js';

/** numpy `np.round(x, 0)` — round half to even (banker's rounding). */
export function npRound0(x: number): number {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff < 0.5) return floor;
  if (diff > 0.5) return floor + 1;
  // exact .5 → round to the even neighbour
  return floor % 2 === 0 ? floor : floor + 1;
}

/** histogram.py:_trim — strip trailing zeros after the decimal point only. */
function trim(s: string): string {
  if (s.includes('.')) {
    return s.replace(/0+$/, '').replace(/\.$/, '');
  }
  return s;
}

/** histogram.py:fmt_num — SI prefix (K/M/B/T) + step-based precision. */
export function fmtNum(value: number, step: number, ref: number): string {
  if (step > 0 && Math.abs(value) < step * 1e-9) {
    value = 0.0;
  }
  const tiers: Array<[number, string]> = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ];
  for (const [threshold, suffix] of tiers) {
    if (ref >= threshold) {
      const scaled = value / threshold;
      const stepS = step / threshold;
      let dec = stepS > 0 ? Math.max(0, -Math.floor(Math.log10(stepS)) + 1) : 1;
      dec = Math.min(dec, 2);
      return trim(scaled.toFixed(dec)) + suffix;
    }
  }
  let dec = step > 0 ? Math.max(0, -Math.floor(Math.log10(step)) + 1) : 0;
  dec = Math.min(dec, 6);
  return trim(value.toFixed(dec));
}

/**
 * histogram.py:_join_bounds — any negative bound switches the separator to
 * `<>`; the minus sign and en-dash are near-identical glyphs and `-0.5–0.5`
 * reads as a double dash.
 */
function joinBounds(loS: string, hiS: string): string {
  const sep = loS.startsWith('-') || hiS.startsWith('-') ? '<>' : '–';
  return `${loS}${sep}${hiS}`;
}

/** histogram.py:fmt_bucket */
export function fmtBucket(lo: number, hi: number, step: number, ref: number): string {
  return joinBounds(fmtNum(lo, step, ref), fmtNum(hi, step, ref));
}

/**
 * histogram.py:fmt_tail_bucket — per-bound SI prefix (ref = |bound|) so a far
 * outlier bound doesn't drag a small bound down to '0K'.
 */
function fmtTailBucket(lo: number, hi: number, step: number): string {
  return joinBounds(fmtNum(lo, step, Math.abs(lo)), fmtNum(hi, step, Math.abs(hi)));
}

/** histogram.py:numeric_histogram_labels — one label per bucket from the edges. */
export function numericHistogramLabels(endpoints: number[]): string[] {
  let left = endpoints[0];
  const labels: string[] = [];
  const minVal = endpoints[0];
  const maxVal = endpoints[endpoints.length - 1];
  const step = (maxVal - minVal) / Math.max(endpoints.length - 1, 1);
  const ref = Math.max(Math.abs(minVal), Math.abs(maxVal));
  for (const edge of endpoints.slice(1)) {
    labels.push(fmtBucket(left, edge, step, ref));
    left = edge;
  }
  return labels;
}

/**
 * The raw numeric-histogram inputs, mirroring Python's `histogram_args`:
 *   - `meatCounts`        — np.histogram bin counts (10 bins).
 *   - `endpoints`         — the 11 bin edges (linspace over the meat range).
 *   - `lowTail`/`highTail`— the 1st/99th percentile cut points.
 * `normalizedPopulations` is derived here (counts / sum) so callers only carry
 * the SQL-shaped values.
 */
export interface NumericHistogramArgs {
  meatCounts: number[];
  endpoints: number[];
  lowTail: number;
  highTail: number;
}

/** histogram.py:numeric_histogram */
export function numericHistogram(
  args: NumericHistogramArgs,
  min: number,
  max: number,
  nanPer: number,
): HistogramBar[] {
  const naObs: HistogramBar = { name: 'NA', NA: npRound0(nanPer * 100) };
  if (nanPer === 1.0) return [naObs];

  const { meatCounts, endpoints, lowTail, highTail } = args;
  const total = meatCounts.reduce((a, b) => a + b, 0);
  const normalizedPop = meatCounts.map((c) => (total > 0 ? c / total : 0));
  const labels = numericHistogramLabels(endpoints);

  const eLo = endpoints[0];
  const eHi = endpoints[endpoints.length - 1];
  const step = (eHi - eLo) / Math.max(endpoints.length - 1, 1);

  const histo: HistogramBar[] = [];
  histo.push({ name: fmtTailBucket(min, lowTail, step), tail: 1 });
  labels.forEach((label, i) => {
    histo.push({ name: label, population: npRound0(normalizedPop[i] * 100) });
  });
  histo.push({ name: fmtTailBucket(highTail, max, step), tail: 1 });
  if (nanPer > 0.0) histo.push(naObs);
  return histo;
}

/** A distinct value and its row count, as returned by the value-counts query. */
export interface ValueCount {
  name: string;
  count: number;
}

/**
 * histogram.py:categorical_histogram (with categorical_dict inlined).
 *
 * `top` is the top-N value counts (already sorted desc); `restSum` is the
 * summed count of every other distinct value; `uniqueCount` is the number of
 * distinct values that occur exactly once (over the whole column). `length`
 * includes nulls.
 */
export function categoricalHistogram(
  length: number,
  top: ValueCount[],
  restSum: number,
  uniqueCount: number,
  nanPer: number,
): HistogramBar[] {
  const histo: HistogramBar[] = [];
  for (const { name, count } of top) {
    const percent = npRound0((count / length) * 100);
    if (percent > 0.3) {
      histo.push({ name: String(name), cat_pop: percent });
    }
  }
  const longTail = restSum - uniqueCount;
  if (longTail > 0) {
    histo.push({ name: 'longtail', longtail: npRound0((longTail / length) * 100) });
  }
  if (uniqueCount > 0) {
    histo.push({ name: 'unique', unique: npRound0((uniqueCount / length) * 100) });
  }
  if (nanPer > 0.0) {
    histo.push({ name: 'NA', NA: npRound0(nanPer * 100) });
  }
  return histo;
}

/** The categorical inputs `buildHistogram` needs (see `parseCategorical`). */
export interface CategoricalArgs {
  top: ValueCount[];
  restSum: number;
  uniqueCount: number;
}

/**
 * histogram.py:histogram — pick the numeric path only when the column is
 * numeric, has more than 5 distinct values, valid histogram args, and the
 * resulting numeric histogram has more than 5 bars; otherwise fall back to the
 * categorical histogram.
 *
 * The numeric and categorical inputs are fetched lazily so the categorical
 * query only runs when the numeric path doesn't win — matching histogram.py's
 * short-circuit. This is the single dispatcher: the production pipeline
 * (histogramSql.ts:computeColumnHistogram) supplies SQL-backed fetchers, the
 * unit tests supply in-memory ones, so the same branch logic is what ships.
 */
export async function buildHistogram(opts: {
  isNumeric: boolean;
  distinctCount: number;
  length: number;
  nanPer: number;
  min: number | null;
  max: number | null;
  fetchNumericArgs: () => Promise<NumericHistogramArgs | null>;
  fetchCategorical: () => Promise<CategoricalArgs>;
}): Promise<HistogramBar[]> {
  const { isNumeric, distinctCount, length, nanPer, min, max, fetchNumericArgs, fetchCategorical } =
    opts;
  if (isNumeric && distinctCount > 5 && min !== null && max !== null) {
    const numericArgs = await fetchNumericArgs();
    if (numericArgs) {
      const temp = numericHistogram(numericArgs, min, max, nanPer);
      if (temp.length > 5) return temp;
    }
  }
  const categorical = await fetchCategorical();
  return categoricalHistogram(length, categorical.top, categorical.restSum, categorical.uniqueCount, nanPer);
}
