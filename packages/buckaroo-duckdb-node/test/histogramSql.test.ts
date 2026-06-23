import { describe, it, expect } from 'vitest';
import {
  numericHistogramSql,
  categoricalHistogramSql,
  parseNumericArgs,
  parseCategorical,
  MEAT_BINS,
} from '../src/histogramSql';

describe('numericHistogramSql', () => {
  const sql = numericHistogramSql('SELECT * FROM t', 'a');

  it('clips the meat to the 1st/99th percentile via quantile_cont', () => {
    expect(sql).toContain('quantile_cont("a", 0.01)');
    expect(sql).toContain('quantile_cont("a", 0.99)');
  });

  it('buckets the meat into 10 equal-width bins', () => {
    expect(sql).toContain(`(_mm.meat_max - _mm.meat_min) / ${MEAT_BINS}.0`);
  });
});

describe('categoricalHistogramSql', () => {
  it('takes the top-N value counts plus the unique aggregate', () => {
    const sql = categoricalHistogramSql('SELECT * FROM t', 'b', 7);
    expect(sql).toContain('GROUP BY "b"');
    expect(sql).toContain('FILTER (WHERE c = 1)');
    expect(sql).toContain('LIMIT 7');
  });
});

describe('parseNumericArgs', () => {
  it('fills the 10-bin counts and derives evenly-spaced endpoints', () => {
    const rows = [
      { low_tail: 1.99, high_tail: 49, meat_min: 2, meat_max: 12, bin: 0, c: 3 },
      { low_tail: 1.99, high_tail: 49, meat_min: 2, meat_max: 12, bin: 2, c: 7 },
    ];
    const args = parseNumericArgs(rows)!;
    expect(args.lowTail).toBe(1.99);
    expect(args.highTail).toBe(49);
    expect(args.meatCounts).toEqual([3, 0, 7, 0, 0, 0, 0, 0, 0, 0]);
    expect(args.endpoints).toHaveLength(MEAT_BINS + 1);
    expect(args.endpoints[0]).toBe(2);
    expect(args.endpoints[MEAT_BINS]).toBeCloseTo(12);
  });

  it('returns null for a degenerate (empty) meat range', () => {
    expect(parseNumericArgs([])).toBeNull();
  });
});

describe('parseCategorical', () => {
  it('derives restSum from non_null minus the top counts', () => {
    const rows = [
      { name: 'bar', c: 50, non_null: 100, unique_count: 10 },
      { name: 'foo', c: 30, non_null: 100, unique_count: 10 },
    ];
    const parsed = parseCategorical(rows);
    expect(parsed.top).toEqual([
      { name: 'bar', count: 50 },
      { name: 'foo', count: 30 },
    ]);
    expect(parsed.restSum).toBe(20);
    expect(parsed.uniqueCount).toBe(10);
  });

  it('handles an all-null column (no rows)', () => {
    expect(parseCategorical([])).toEqual({ top: [], restSum: 0, uniqueCount: 0 });
  });
});
