import { describe, it, expect } from 'vitest';
import {
  summarizeToSDType,
  sdTypeToStatRows,
  sdTypeToWideRow,
  V1_STAT_NAMES,
} from '../src/stats';
import type { SummarizeRow } from '../src/DuckSource';

const summarizeRows: SummarizeRow[] = [
  {
    column_name: 'a',
    column_type: 'BIGINT',
    min: '1',
    max: '1000',
    approx_unique: 950,
    avg: '500.5',
    std: '288.8',
    q25: '250',
    q50: '500',
    q75: '750',
    count: 1000,
    null_percentage: 10, // 10% of 1000 = 100 nulls
  },
  {
    column_name: 'b',
    column_type: 'VARCHAR',
    min: 'aaa',
    max: 'zzz',
    approx_unique: 26,
    avg: null,
    std: null,
    q25: null,
    q50: null,
    q75: null,
    count: 1000,
    null_percentage: 0,
  },
  // the synthesized index column must be ignored
  {
    column_name: 'index',
    column_type: 'BIGINT',
    min: '0',
    max: '999',
    approx_unique: 1000,
    avg: '499.5',
    std: '288',
    q25: '0',
    q50: '0',
    q75: '0',
    count: 1000,
    null_percentage: 0,
  },
];

describe('summarizeToSDType', () => {
  const sd = summarizeToSDType(summarizeRows);

  it('skips the synthesized index column', () => {
    expect(Object.keys(sd)).toEqual(['a', 'b']);
  });

  it('maps SUMMARIZE fields per the v1 plan table', () => {
    expect(sd.a).toMatchObject({
      dtype: 'BIGINT',
      distinct_count: 950,
      mean: 500.5,
      std: 288.8,
      min: 1,
      max: 1000,
      q25: 250,
      q50: 500,
      q75: 750,
    });
  });

  it('derives null_count = count × null_percentage / 100', () => {
    expect(sd.a.null_count).toBe(100);
    expect(sd.b.null_count).toBe(0);
  });

  it('keeps non-numeric min/max as strings and nulls absent stats', () => {
    expect(sd.b.min).toBe('aaa');
    expect(sd.b.max).toBe('zzz');
    expect(sd.b.mean).toBeNull();
    expect(sd.b.std).toBeNull();
  });
});

describe('sdTypeToStatRows', () => {
  const rows = sdTypeToStatRows(summarizeToSDType(summarizeRows));

  it('produces one row per v1 stat, keyed by index/level_0', () => {
    expect(rows).toHaveLength(V1_STAT_NAMES.length);
    expect(rows.map((r) => r.index)).toEqual([...V1_STAT_NAMES]);
    expect(rows[0].level_0).toBe('dtype');
  });

  it('places each column value under its alias key', () => {
    const meanRow = rows.find((r) => r.index === 'mean')!;
    expect(meanRow.a).toBe(500.5);
    expect(meanRow.b).toBeNull();
    const dtypeRow = rows.find((r) => r.index === 'dtype')!;
    expect(dtypeRow.a).toBe('BIGINT');
    expect(dtypeRow.b).toBe('VARCHAR');
  });
});

describe('sdTypeToWideRow', () => {
  it('builds {col}__{stat} keys', () => {
    const wide = sdTypeToWideRow(summarizeToSDType(summarizeRows));
    expect(wide.a__dtype).toBe('BIGINT');
    expect(wide.a__mean).toBe(500.5);
    expect(wide.b__null_count).toBe(0);
  });
});
