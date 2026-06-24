/**
 * The Dastardly Dataframe Dataset, DuckDB edition.
 *
 * Ports the pathologies from buckaroo's `ddd_library.py` ("the weirdest
 * dataframes that cause trouble frequently") that survive translation to a SQL
 * relation. The MultiIndex column/row frames, named indexes, and tuple columns
 * are pandas *display* shapes with no DuckDB analog, so they're out of scope —
 * but every data/dtype pathology below maps to a real DuckDB column and is
 * exactly where this backend can misbehave.
 *
 * Reaches a real DuckDB via @duckdb/node-api and skips on CI (`SKIP_DUCKDB=1`),
 * matching spike.duckdb.test.ts.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { parquetReadObjects, asyncBufferFromFile } from 'hyparquet';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

import { DuckBackend } from '../src/backend';
import { createNodeApiDuckSource } from '../src/adapters/nodeApiDuckSource';
import type { DuckDBConnectionLike } from '../src/adapters/nodeApiDuckSource';
import type { DuckSource } from '../src/DuckSource';
import type { PayloadResponse } from '../src/wireTypes';

let connection: DuckDBConnectionLike | undefined;
let source: DuckSource | undefined;

beforeAll(async () => {
  try {
    const duck = await import('@duckdb/node-api');
    const instance = await duck.DuckDBInstance.create(':memory:');
    connection = (await instance.connect()) as unknown as DuckDBConnectionLike;
    source = createNodeApiDuckSource(connection);
  } catch (err) {
    console.warn('[ddd] @duckdb/node-api not available, skipping:', (err as Error).message);
  }
});

async function readParquet(bytes: Uint8Array): Promise<Record<string, unknown>[]> {
  const dir = await mkdtemp(join(tmpdir(), 'buckaroo-ddd-'));
  const file = join(dir, `${randomUUID()}.parquet`);
  try {
    await writeFile(file, bytes);
    const buf = await asyncBufferFromFile(file);
    return (await parquetReadObjects({ file: buf })) as Record<string, unknown>[];
  } finally {
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}

function decodePayload(resp: PayloadResponse): Promise<Record<string, unknown>[]> {
  return readParquet(Buffer.from(resp.payload.data, 'base64'));
}

/** Pull one full window of rows back through COPY → parquet → hyparquet. */
async function readRows(backend: DuckBackend): Promise<Record<string, unknown>[]> {
  const resp = await backend.handleInfiniteRequest({
    sourceName: 'main',
    start: 0,
    end: 100,
    origEnd: 100,
  });
  return decodePayload(resp);
}

/** The pivoted stat rows the viewer consumes (json envelope). */
function statData(msg: Awaited<ReturnType<DuckBackend['initialState']>>): Array<Record<string, unknown>> {
  return (msg.df_data_dict.all_stats as { format: string; data: Array<Record<string, unknown>> }).data;
}

describe.runIf(process.env.SKIP_DUCKDB !== '1')('ddd: dastardly dataframes (DuckDB backend)', () => {
  // ddd_library.py:df_with_col_named_index — a column literally named "index".
  // Dangerous here because the backend synthesizes its own `index` column
  // (rename.ts:INDEX_COL) via ROW_NUMBER. The user column must survive without
  // colliding with it.
  it('df_with_col_named_index: a user "index" column survives alongside the synthesized index', async () => {
    if (!source) return;
    const backend = new DuckBackend(
      source,
      `SELECT * FROM (VALUES ('asdf','7777'),('foo_b','ooooo'),('bar_a','--- -')) t(a, "index")`,
    );
    const msg = await backend.initialState();
    const cfg = msg.df_display_args.main.df_viewer_config;

    // both source columns kept; the user 'index' is aliased to something other
    // than 'index' so it never clashes with the ROW_NUMBER column.
    expect(cfg.column_config.map((c) => c.header_name)).toEqual(['a', 'index']);
    const userIndex = cfg.column_config.find((c) => c.header_name === 'index')!;
    expect(userIndex.col_name).not.toBe('index');
    expect(msg.df_meta.total_rows).toBe(3);

    const rows = await readRows(backend);
    // synthesized index 0..2 and the user 'index' values coexist in the window
    expect(rows.map((r) => r.index)).toEqual([0n, 1n, 2n]);
    expect(rows.map((r) => r[userIndex.col_name])).toEqual(['7777', 'ooooo', '--- -']);
  });

  // ddd_library.py:df_with_infinity — [nan, inf, -inf]. SUMMARIZE's STDDEV_SAMP
  // overflows ("out of range") on any non-finite value and would abort the whole
  // stats query, so the stats path (statsRelation) nulls non-finite floats. Here
  // every value is non-finite, so the scalar stats collapse to null — but
  // initialState succeeds and the column still renders.
  it('df_with_infinity: ±inf / nan are treated as missing for stats instead of crashing', async () => {
    if (!source) return;
    const backend = new DuckBackend(
      source,
      `SELECT * FROM (VALUES ('nan'::DOUBLE),('inf'::DOUBLE),('-inf'::DOUBLE)) t(a)`,
    );
    const msg = await backend.initialState(); // no longer throws
    const stats = statData(msg);
    expect(stats.find((r) => r.index === 'dtype')!.a).toBe('DOUBLE');
    expect(stats.find((r) => r.index === 'min')!.a).toBeNull();
    expect(stats.find((r) => r.index === 'std')!.a).toBeNull();
    // the column still gets a histogram bar list (no crash)
    expect(Array.isArray(stats.find((r) => r.index === 'histogram')!.a)).toBe(true);
  });

  // The guard must not throw away finite data: a column mixing finite values with
  // nan/±inf keeps real min/max/std computed over the finite values only.
  it('df_with_infinity (mixed): finite stats survive alongside non-finite values', async () => {
    if (!source) return;
    const backend = new DuckBackend(
      source,
      `SELECT * FROM (VALUES ('inf'::DOUBLE),('-inf'::DOUBLE),('nan'::DOUBLE),(1.5::DOUBLE),(2.5::DOUBLE)) t(a)`,
    );
    const stats = statData(await backend.initialState());
    expect(Number(stats.find((r) => r.index === 'min')!.a)).toBe(1.5);
    expect(Number(stats.find((r) => r.index === 'max')!.a)).toBe(2.5);
    expect(stats.find((r) => r.index === 'std')!.a).not.toBeNull();
  });

  // ddd_library.py:df_with_really_big_number — an int beyond int64. In DuckDB
  // that's HUGEINT, which the v1 paths render through JS `number`: lossy. The
  // categorical histogram, built via CAST(... AS VARCHAR), keeps the exact
  // digits — so the two surfaces disagree, and that's worth pinning.
  it('df_with_really_big_number: HUGEINT > 2^63 is lossy in stats/rows but exact in the histogram label', async () => {
    if (!source) return;
    const backend = new DuckBackend(
      source,
      `SELECT * FROM (VALUES (9999999999999999999::HUGEINT),(1::HUGEINT)) t(col1)`,
    );
    const msg = await backend.initialState();
    const stats = statData(msg);

    expect(stats.find((r) => r.index === 'dtype')!.a).toBe('HUGEINT');
    // max goes through Number() → 9999999999999999999 rounds up to 1e19 (lossy)
    expect(stats.find((r) => r.index === 'max')!.a).toBe(10000000000000000000);
    // the histogram label preserves the exact value (VARCHAR cast, not numeric)
    const histo = stats.find((r) => r.index === 'histogram')!.a as Array<{ name: string }>;
    expect(histo.map((b) => b.name)).toContain('9999999999999999999');

    // the row path is lossy too: HUGEINT serializes as parquet DOUBLE
    const rows = await readRows(backend);
    expect(rows.map((r) => r.a).sort()).toEqual([1, 10000000000000000000]);
  });

  // ddd_library.py:pl_df_with_weird_types — Duration/Time/Categorical/Decimal/
  // Binary. The DuckDB analogs are INTERVAL/TIME/ENUM/DECIMAL/BLOB. None should
  // crash initialState; each gets a displayer and a histogram.
  const WEIRD_STMT = `SELECT
    'red'::ENUM('red','green','blue') AS categorical,
    INTERVAL 1 HOUR AS duration,
    TIME '14:30:00' AS t,
    100.50::DECIMAL(10,2) AS dec,
    'hello'::BLOB AS binary,
    10 AS int_col`;

  it('pl_df_with_weird_types: assigns a displayer + histogram to every exotic dtype', async () => {
    if (!source) return;
    const msg = await new DuckBackend(source, WEIRD_STMT).initialState();
    const cfg = msg.df_display_args.main.df_viewer_config;

    const byHeader = Object.fromEntries(
      cfg.column_config.map((c) => [c.header_name, c.displayer_args.displayer]),
    );
    expect(byHeader).toEqual({
      categorical: 'obj', // ENUM is not mapped to string in v1
      duration: 'obj', // INTERVAL → obj
      t: 'datetimeLocaleString', // TIME → datetime
      dec: 'float', // DECIMAL → float
      binary: 'obj', // BLOB → obj
      int_col: 'float', // integers render through the float displayer (0 frac digits)
    });

    // every column carries a (categorical-fallback) histogram bar list
    const histoRow = statData(msg).find((r) => r.index === 'histogram')!;
    for (const c of cfg.column_config) {
      expect(Array.isArray(histoRow[c.col_name])).toBe(true);
    }
  });

  it('pl_df_with_weird_types: COPY serializes every exotic dtype, but hyparquet cannot decode INTERVAL', async () => {
    if (!source) return;
    const backend = new DuckBackend(source, WEIRD_STMT);
    const resp = await backend.handleInfiniteRequest({
      sourceName: 'main',
      start: 0,
      end: 100,
      origEnd: 100,
    });
    // the backend never coerces — COPY → parquet succeeds for all of them
    expect(resp.payload.format).toBe('parquet_b64');
    // but the reader chokes on the INTERVAL column: a v1 row-path limitation
    await expect(decodePayload(resp)).rejects.toThrow(/interval not supported/i);

    // drop INTERVAL and the rest round-trips cleanly (aliases shift up by one)
    const rows = await readRows(
      new DuckBackend(source, WEIRD_STMT.replace('INTERVAL 1 HOUR AS duration,', '')),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].a).toBe('red'); // ENUM → string
    expect(rows[0].c).toBe(100.5); // DECIMAL → double
    expect(rows[0].e).toBe(10); // int_col
  });
});
