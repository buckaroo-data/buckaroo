import { describe, it, expect } from 'vitest';
import {
  npRound0,
  fmtBucket,
  numericHistogram,
  numericHistogramLabels,
  categoricalHistogram,
  buildHistogram,
  type NumericHistogramArgs,
} from '../src/histogram';

// Ground-truth assertions ported from the Python producer's tests
// (tests/unit/histogram_test.py, polars_categorical_histogram_test.py) so a
// DuckDB column renders the exact same bars as pandas/polars.

describe('npRound0 (numpy round-half-to-even)', () => {
  it.each([
    [2.5, 2],
    [3.5, 4],
    [0.5, 0],
    [1.5, 2],
    [2.4, 2],
    [2.6, 3],
    [33.0, 33],
  ])('round(%f) → %i', (x, expected) => {
    expect(npRound0(x)).toBe(expected);
  });
});

describe('fmtBucket (histogram_test.py:test_fmt_bucket_labels)', () => {
  it('SI prefix with step-scaled precision', () => {
    expect(fmtBucket(300, 2200, 190, 2200)).toBe('0.3K–2.2K');
  });
  it('negative high bound switches the separator to avoid the double-dash', () => {
    expect(fmtBucket(-100, -80, 2, 100)).toBe('-100<>-80');
  });
  it('negative low bound too', () => {
    expect(fmtBucket(-0.5, 0.5, 0.1, 0.5)).toBe('-0.5<>0.5');
  });
  it('step=0 (constant column) must not crash', () => {
    expect(fmtBucket(7, 7, 0, 7)).toBe('7–7');
  });
});

describe('numericHistogramLabels', () => {
  it('produces one label per bucket from the edges', () => {
    expect(numericHistogramLabels([1.4, 1.6, 1.8])).toEqual(['1.4–1.6', '1.6–1.8']);
  });
});

describe('numericHistogram (histogram_test.py:test_tail_label_precision)', () => {
  const args: NumericHistogramArgs = {
    meatCounts: [5, 5],
    endpoints: [1.4, 1.6, 1.8],
    lowTail: 1.4,
    highTail: 1.8,
  };

  it('tail labels take precision from the meat width, not the outlier range', () => {
    const result = numericHistogram(args, 1.2, 50_000, 0.0);
    expect(result[0]).toEqual({ name: '1.2–1.4', tail: 1 });
    expect(result[result.length - 1]).toEqual({ name: '1.8–50K', tail: 1 });
  });

  it('emits low tail, meat populations (0–100 %), high tail', () => {
    expect(numericHistogram(args, 1.2, 1.9, 0.0)).toEqual([
      { name: '1.2–1.4', tail: 1 },
      { name: '1.4–1.6', population: 50 },
      { name: '1.6–1.8', population: 50 },
      { name: '1.8–1.9', tail: 1 },
    ]);
  });

  it('appends an NA bucket when there are nulls', () => {
    const result = numericHistogram(args, 1.2, 1.9, 0.25);
    expect(result[result.length - 1]).toEqual({ name: 'NA', NA: 25 });
  });

  it('all-null column collapses to a single NA bar', () => {
    expect(numericHistogram(args, 1.2, 1.9, 1.0)).toEqual([{ name: 'NA', NA: 100 }]);
  });
});

describe('categoricalHistogram (histogram.py parity, 0–100 scale)', () => {
  it('top categories become cat_pop bars', () => {
    expect(
      categoricalHistogram(
        100,
        [
          { name: 'A', count: 50 },
          { name: 'B', count: 30 },
          { name: 'C', count: 20 },
        ],
        0,
        0,
        0,
      ),
    ).toEqual([
      { name: 'A', cat_pop: 50 },
      { name: 'B', cat_pop: 30 },
      { name: 'C', cat_pop: 20 },
    ]);
  });

  it('longtail and unique come last (test_categorical_mixed_frequencies)', () => {
    expect(
      categoricalHistogram(
        100,
        [
          { name: 'bar', count: 50 },
          { name: 'foo', count: 30 },
        ],
        20, // restSum
        10, // uniqueCount → longtail = 20 - 10 = 10
        0,
      ),
    ).toEqual([
      { name: 'bar', cat_pop: 50 },
      { name: 'foo', cat_pop: 30 },
      { name: 'longtail', longtail: 10 },
      { name: 'unique', unique: 10 },
    ]);
  });

  it('appends an NA bucket when there are nulls', () => {
    const bars = categoricalHistogram(100, [{ name: 'A', count: 67 }], 0, 0, 0.33);
    expect(bars[bars.length - 1]).toEqual({ name: 'NA', NA: 33 });
  });
});

describe('buildHistogram dispatcher (histogram.py:histogram)', () => {
  const numericArgs: NumericHistogramArgs = {
    meatCounts: [1, 2, 3, 4, 5, 4, 3, 2, 1, 1],
    endpoints: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    lowTail: 0,
    highTail: 10,
  };
  const categorical = { top: [{ name: 'x', count: 8 }], restSum: 0, uniqueCount: 0 };

  it('uses the numeric histogram when numeric with >5 distinct values', () => {
    const bars = buildHistogram({
      isNumeric: true,
      distinctCount: 50,
      length: 100,
      nanPer: 0,
      min: -1,
      max: 11,
      numericArgs,
      categorical,
    });
    // low tail + 10 meat + high tail = 12 bars
    expect(bars).toHaveLength(12);
    expect(bars.some((b) => b.population !== undefined)).toBe(true);
  });

  it('falls back to categorical for low-cardinality numeric columns', () => {
    const bars = buildHistogram({
      isNumeric: true,
      distinctCount: 3,
      length: 100,
      nanPer: 0,
      min: 0,
      max: 2,
      numericArgs,
      categorical,
    });
    expect(bars).toEqual([{ name: 'x', cat_pop: 8 }]);
  });

  it('falls back to categorical when numeric args are missing (degenerate meat)', () => {
    const bars = buildHistogram({
      isNumeric: true,
      distinctCount: 50,
      length: 100,
      nanPer: 0,
      min: 0,
      max: 2,
      numericArgs: null,
      categorical,
    });
    expect(bars).toEqual([{ name: 'x', cat_pop: 8 }]);
  });
});
