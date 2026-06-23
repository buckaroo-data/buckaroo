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
import type { DuckSource } from '../src/DuckSource';

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
});
