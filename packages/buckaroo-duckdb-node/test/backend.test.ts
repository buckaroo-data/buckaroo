import { describe, it, expect } from 'vitest';
import { DuckBackend } from '../src/backend';
import type { DuckSource, DescribeRow, SummarizeRow } from '../src/DuckSource';

/**
 * A fake DuckSource — exercises the orchestrator (rename → stats → config →
 * windowed-SQL → envelope) without a native DuckDB. The real round-trip is
 * covered by spike.duckdb.test.ts.
 */
function fakeSource(): DuckSource & { lastCopyQuery?: string } {
  const src: DuckSource & { lastCopyQuery?: string } = {
    async describe(): Promise<DescribeRow[]> {
      return [
        { name: 'price', type: 'DOUBLE' },
        { name: 'name', type: 'VARCHAR' },
      ];
    },
    async summarize(): Promise<SummarizeRow[]> {
      return [
        {
          column_name: 'a',
          column_type: 'DOUBLE',
          min: '1.5',
          max: '9.5',
          approx_unique: 5,
          avg: '5.0',
          std: '2.0',
          q25: '2',
          q50: '5',
          q75: '8',
          count: 42,
          null_percentage: 0,
        },
        {
          column_name: 'b',
          column_type: 'VARCHAR',
          min: 'a',
          max: 'z',
          approx_unique: 7,
          avg: null,
          std: null,
          q25: null,
          q50: null,
          q75: null,
          count: 42,
          null_percentage: 0,
        },
        {
          column_name: 'index',
          column_type: 'BIGINT',
          min: '0',
          max: '41',
          approx_unique: 42,
          avg: '20.5',
          std: '12',
          q25: '10',
          q50: '20',
          q75: '31',
          count: 42, // total rows
          null_percentage: 0,
        },
      ];
    },
    async queryRows(): Promise<Array<Record<string, unknown>>> {
      // both columns are low-cardinality here (approx_unique ≤ 7), so only the
      // categorical value-counts query runs; return a single dominant category.
      return [{ name: 'x', c: 42, non_null: 42, unique_count: 0 }];
    },
    async copyToParquet(query: string): Promise<Uint8Array> {
      src.lastCopyQuery = query;
      return new Uint8Array([1, 2, 3, 4]);
    },
  };
  return src;
}

describe('DuckBackend.initialState', () => {
  it('builds a read-only viewer initial_state with renamed columns + stats', async () => {
    const backend = new DuckBackend(fakeSource(), 'SELECT * FROM t');
    const msg = await backend.initialState();

    expect(msg.type).toBe('initial_state');
    // total derived from the index column's SUMMARIZE count
    expect(msg.df_meta.total_rows).toBe(42);
    expect(msg.df_meta.columns).toBe(2);

    const cfg = msg.df_display_args.main.df_viewer_config;
    expect(cfg.column_config.map((c) => c.col_name)).toEqual(['a', 'b']);
    expect(cfg.column_config[0].header_name).toBe('price');

    // the live infinite source MUST be keyed 'main' — the viewer only wires the
    // on-demand datasource for that exact key; any other key renders empty.
    expect(msg.df_display_args.main.data_key).toBe('main');
    // main rows are empty (delivered via infinite_request); stats are inline json
    expect(msg.df_data_dict.main).toEqual([]);
    const stats = msg.df_data_dict.all_stats as {
      format: string;
      data: Array<Record<string, unknown>>;
    };
    expect(stats.format).toBe('json');
    expect(stats.data.length).toBeGreaterThan(0);

    // the histogram pinned row sits right after dtype and carries a bar list
    // per column (categorical fallback here)
    expect(cfg.pinned_rows[1]).toEqual({
      primary_key_val: 'histogram',
      displayer_args: { displayer: 'histogram' },
    });
    const histoRow = stats.data.find((r) => r.index === 'histogram')!;
    expect(stats.data.indexOf(histoRow)).toBe(1);
    expect(histoRow.a).toEqual([{ name: 'x', cat_pop: 100 }]);
    expect(histoRow.b).toEqual([{ name: 'x', cat_pop: 100 }]);
  });
});

describe('DuckBackend.handleInfiniteRequest', () => {
  it('emits a parquet_b64 envelope and a windowed/sorted query', async () => {
    const src = fakeSource();
    const backend = new DuckBackend(src, 'SELECT * FROM t');
    await backend.initialState(); // establishes total + plan

    const resp = await backend.handleInfiniteRequest({
      sourceName: 'main',
      start: 0,
      end: 10,
      origEnd: 10,
      sort: 'a',
      sort_direction: 'desc',
    });

    expect(resp.type).toBe('infinite_resp');
    expect(resp.length).toBe(42);
    expect(resp.payload).toEqual({
      format: 'parquet_b64',
      data: Buffer.from([1, 2, 3, 4]).toString('base64'),
    });
    expect(src.lastCopyQuery).toContain('ORDER BY a DESC, index ASC');
    expect(src.lastCopyQuery).toContain('LIMIT 10 OFFSET 0');
  });
});
