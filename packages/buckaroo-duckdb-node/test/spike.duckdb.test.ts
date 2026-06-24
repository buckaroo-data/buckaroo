/**
 * Spike: prove the transport's serialization layer end to end, before any
 * histogram SQL (plan §"The spike", step 1 + step 3). This is the part of the
 * spike that does NOT depend on #933.
 *
 *   1. Serialization fidelity + latency — COPY mixed BIGINT>2^53, DECIMAL(38,9),
 *      DATE, TIMESTAMP, NULL to a tempfile parquet, read it back with hyparquet,
 *      assert fidelity AND measure the per-window COPY→read round-trip.
 *   3. Stats round-trip — SUMMARIZE → SDType → pivoted stat rows.
 *
 * Reaches a real DuckDB instance via @duckdb/node-api. If that native module
 * isn't installed the suite skips (it's an optional peer dep).
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { parquetReadObjects, asyncBufferFromFile } from 'hyparquet';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

import { createNodeApiDuckSource } from '../src/adapters/nodeApiDuckSource';
import type { DuckDBConnectionLike } from '../src/adapters/nodeApiDuckSource';
import { buildRenamePlan } from '../src/rename';
import { effectiveQuery, windowedQuery } from '../src/query';
import { summarizeToSDType, sdTypeToStatRows } from '../src/stats';
import { numericHistogramSql, parseNumericArgs, computeHistograms } from '../src/histogramSql';
import { numericHistogram } from '../src/histogram';
import { DuckBackend } from '../src/backend';
import type { DuckSource } from '../src/DuckSource';

// The exact integer column from the Python producer's histogram test
// (tests/unit/histogram_test.py:INT_ARR). DuckDB's quantile_cont +
// width_bucket must reproduce numpy's 1st/99th-percentile meat histogram.
const INT_ARR = [
  33, 41, 11, 46, 42, 44, 31, 25, 16, 24, 26, 7, 19, 23, 20, 46, 10, 4, 31, 45, 40, 37, 48, 21,
  19, 20, 19, 14, 14, 26, 36, 24, 21, 41, 19, 17, 24, 27, 32, 30, 19, 49, 22, 20, 16, 7, 45, 10,
  23, 44, 28, 44, 15, 29, 34, 3, 44, 19, 20, 27, 1, 35, 34, 42, 12, 9, 21, 32, 40, 41, 49, 47,
  16, 25, 20, 11, 28, 13, 30, 6, 34, 16, 37, 21, 7, 34, 34, 29, 24, 2, 7, 17, 13, 22, 13, 32, 11,
  24, 24, 31, 11, 9, 39, 40, 36, 20, 46, 31, 37, 27, 25, 9, 27, 41, 13, 35, 33, 24, 8, 25, 12, 28,
  26, 17, 7, 18, 12, 6, 45, 42, 32, 38, 31, 25, 33, 13, 24, 23, 40, 18, 33, 42, 7, 40, 48, 29, 27,
  13, 38, 35, 33, 24, 40, 19, 47, 38, 8, 3, 6, 48, 9, 17, 13, 46, 6, 3, 34, 43, 6, 9, 28, 4, 49,
  10, 14, 36, 48, 39, 1, 37, 41, 37, 43, 43, 6, 23, 6, 30, 27, 11, 19, 19, 34, 14, 37, 42, 15, 6,
  48, 32,
];

// histogram_test.py:_assert_ha — the expected normalized meat populations.
const EXPECTED_NORMALIZED = [
  0.07179487179487179, 0.1076923076923077, 0.08205128205128205, 0.1282051282051282,
  0.09743589743589744, 0.1076923076923077, 0.1282051282051282, 0.07692307692307693,
  0.1076923076923077, 0.09230769230769231,
];

// Dynamically import the optional native module; skip the suite if absent.
let connection: DuckDBConnectionLike | undefined;
let source: DuckSource | undefined;

async function readParquet(bytes: Uint8Array): Promise<Record<string, unknown>[]> {
  const dir = await mkdtemp(join(tmpdir(), 'buckaroo-spike-'));
  const file = join(dir, `${randomUUID()}.parquet`);
  try {
    await writeFile(file, bytes);
    const buf = await asyncBufferFromFile(file);
    return (await parquetReadObjects({ file: buf })) as Record<string, unknown>[];
  } finally {
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}

beforeAll(async () => {
  try {
    const duck = await import('@duckdb/node-api');
    const instance = await duck.DuckDBInstance.create(':memory:');
    connection = (await instance.connect()) as unknown as DuckDBConnectionLike;
    source = createNodeApiDuckSource(connection);
  } catch (err) {
    console.warn(
      '[spike] @duckdb/node-api not available, skipping DuckDB spike:',
      (err as Error).message,
    );
  }
});

// A statement exercising the fidelity-critical types. Column → alias:
//   big64 (BIGINT > 2^53) → a, huge (HUGEINT) → b, dec (DECIMAL(38,9)) → c,
//   d (DATE) → d, ts (TIMESTAMP) → e, name (nullable VARCHAR) → f.
const MIXED_STMT = `
  SELECT
    (9007199254740993 + i)::BIGINT AS big64,
    (i * 1000000000)::HUGEINT + 9007199254740993 AS huge,
    (i + 0.123456789)::DECIMAL(38,9) AS dec,
    DATE '2020-01-01' + i::INTEGER AS d,
    TIMESTAMP '2020-01-01 00:00:00' + to_hours(i::INTEGER) AS ts,
    CASE WHEN i % 7 = 0 THEN NULL ELSE 'row' || i END AS name
  FROM range(0, 101) t(i)
`;

describe.runIf(process.env.SKIP_DUCKDB !== '1')('DuckDB serialization spike', () => {
  it('round-trips mixed types through COPY → parquet → hyparquet with fidelity', async () => {
    if (!source) {
      console.warn('[spike] skipped: no DuckDB');
      return;
    }
    const stmt = effectiveQuery(MIXED_STMT);
    const describe_ = await source.describe(stmt);
    const plan = buildRenamePlan(describe_);

    const t0 = performance.now();
    const windowSql = windowedQuery(stmt, plan, { start: 0, end: 101 });
    const bytes = await source.copyToParquet(windowSql);
    const copyMs = performance.now() - t0;

    const rows = await readParquet(bytes);
    const readMs = performance.now() - t0 - copyMs;

    expect(rows).toHaveLength(101);

    // index synthesized 0..100, in order
    expect(rows[0].index).toBe(0n);
    expect(rows[100].index).toBe(100n);

    // BIGINT above 2^53 survives EXACTLY as a bigint — the plan's core fidelity
    // requirement and the whole reason for the COPY→parquet no-coercion path.
    // 9007199254740993 = 2^53 + 1, unrepresentable as a JS number.
    expect(typeof rows[0].a).toBe('bigint');
    expect(rows[0].a).toBe(9007199254740993n);
    expect(rows[1].a).toBe(9007199254740994n);

    // NULL preserved (row 0: i%7==0 → name NULL)
    expect(rows[0].f).toBeNull();
    expect(rows[1].f).toBe('row1');

    // DATE / TIMESTAMP decode to JS Date instants (TZ-independent underlying value)
    expect(rows[0].d).toBeInstanceOf(Date);
    expect(rows[0].e).toBeInstanceOf(Date);

    // DOCUMENTED v1 LIMITATIONS (spike findings, not bugs in this code):
    //  - HUGEINT: DuckDB COPY serializes it as parquet DOUBLE, so values above
    //    2^53 are lossy. Out of the plan's required fidelity set.
    //  - DECIMAL(38,9): hyparquet decodes parquet DECIMAL as a JS double, so
    //    high-precision decimals are not exact. Matches the plan: "v1 casts
    //    DECIMAL → DOUBLE; exactness tracked in #934".
    expect(typeof rows[1].b).toBe('number'); // HUGEINT → double
    expect(typeof rows[0].c).toBe('number'); // DECIMAL → double

    // latency visibility (not an assertion threshold — the plan's open question)
    console.log(
      `[spike] 101-row window: COPY=${copyMs.toFixed(1)}ms read=${readMs.toFixed(1)}ms`,
    );
    // a generous ceiling so a pathological environment still flags
    expect(copyMs).toBeLessThan(5000);
  });

  it('SUMMARIZE → SDType → pivoted stat rows', async () => {
    if (!source) return;
    const stmt = effectiveQuery(MIXED_STMT);
    const plan = buildRenamePlan(await source.describe(stmt));
    const summarizeRows = await source.summarize(plan.renamedRelation(stmt));
    const sd = summarizeToSDType(summarizeRows);

    // alias a is big64 (BIGINT, 9007199254740993 + i for i in 0..100)
    expect(sd.a.dtype).toContain('INT');
    expect(Number(sd.a.min)).toBe(9007199254740993);
    expect(Number(sd.a.max)).toBe(9007199254740993 + 100);
    expect(sd.a.distinct_count).not.toBeNull();

    const rows = sdTypeToStatRows(sd);
    const dtypeRow = rows.find((r) => r.index === 'dtype')!;
    expect(dtypeRow.a).toContain('INT');
    // 'name' (alias f): 101 rows, ~15 nulls (i%7==0 for i in 0..100)
    const nullRow = rows.find((r) => r.index === 'null_count')!;
    expect(Number(nullRow.f)).toBeGreaterThan(0);
  });

  it('numeric histogram clips to the 1st/99th percentile and matches numpy', async () => {
    if (!source) return;
    const stmt = effectiveQuery(`SELECT unnest([${INT_ARR.join(',')}]) AS a`);
    const plan = buildRenamePlan(await source.describe(stmt));
    const relation = plan.renamedRelation(stmt);

    const argRows = await source.queryRows(numericHistogramSql(relation, 'a'));
    const args = parseNumericArgs(argRows)!;

    // 1st/99th percentile cut points (np.quantile linear == quantile_cont)
    expect(args.lowTail).toBeCloseTo(1.99, 5);
    expect(args.highTail).toBeCloseTo(49, 5);

    // 10 meat bins whose normalized populations match the numpy fixture
    expect(args.meatCounts).toHaveLength(10);
    const total = args.meatCounts.reduce((a, b) => a + b, 0);
    const normalized = args.meatCounts.map((c) => c / total);
    normalized.forEach((p, i) => expect(p).toBeCloseTo(EXPECTED_NORMALIZED[i], 6));

    // the rendered bars: low tail, 10 populations, high tail (no nulls → no NA)
    const bars = numericHistogram(args, 1, 49, 0);
    expect(bars).toHaveLength(12);
    expect(bars[0].tail).toBe(1);
    expect(bars[11].tail).toBe(1);
    expect(bars.slice(1, 11).every((b) => typeof b.population === 'number')).toBe(true);
  });

  it('categorical histogram emits cat_pop bars for a string column', async () => {
    if (!source) return;
    // counts 4/3/3 (length 10) — no singleton category, so no unique/longtail bar
    const stmt = effectiveQuery(
      `SELECT unnest(['A','A','A','A','B','B','B','C','C','C']) AS cat`,
    );
    const plan = buildRenamePlan(await source.describe(stmt));
    const relation = plan.renamedRelation(stmt);
    const summarizeRows = await source.summarize(relation);
    const sd = summarizeToSDType(summarizeRows);

    const histos = await computeHistograms(source, relation, plan, sd, 10);
    expect(histos.a).toEqual([
      { name: 'A', cat_pop: 40 },
      { name: 'B', cat_pop: 30 },
      { name: 'C', cat_pop: 30 },
    ]);
  });

  it('search filters rows, stats counts, and highlights end to end', async () => {
    if (!source) return;
    const stmt = `SELECT * FROM (VALUES ('Alice', 1), ('Bob', 2), ('Charlie', 3), ('Alfred', 4)) t(name, n)`;
    const backend = new DuckBackend(source, stmt);

    const full = await backend.initialState();
    expect(full.df_meta.total_rows).toBe(4);
    expect(full.df_meta.filtered_rows).toBe(4);

    // case-sensitive substring 'Al' matches Alice + Alfred, not Bob/Charlie
    backend.setSearch('Al');
    const filtered = await backend.initialState();
    expect(filtered.df_meta.total_rows).toBe(4); // total unchanged
    expect(filtered.df_meta.filtered_rows).toBe(2);

    const strCol = filtered.df_display_args.main.df_viewer_config.column_config.find(
      (c) => c.displayer_args.displayer === 'string',
    )!;
    expect(strCol.displayer_args).toMatchObject({ highlight_phrase: ['Al'] });

    const resp = await backend.handleInfiniteRequest({
      sourceName: 'main',
      start: 0,
      end: 10,
      origEnd: 10,
    });
    expect(resp.length).toBe(2);
    const matchRows = await readParquet(Buffer.from(resp.payload.data, 'base64'));
    expect(matchRows.map((r) => r.a).sort()).toEqual(['Alfred', 'Alice']);

    // clearing the search restores the full view
    backend.setSearch('');
    const restored = await backend.initialState();
    expect(restored.df_meta.filtered_rows).toBe(4);
  });
});
