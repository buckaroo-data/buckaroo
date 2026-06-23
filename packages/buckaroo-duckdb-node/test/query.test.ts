import { describe, it, expect } from 'vitest';
import { effectiveQuery, countQuery, windowedQuery } from '../src/query';
import type { QueryTransform } from '../src/query';
import { buildRenamePlan } from '../src/rename';
import type { DescribeRow } from '../src/DuckSource';

const rows: DescribeRow[] = [
  { name: 'price', type: 'DOUBLE' },
  { name: 'name', type: 'VARCHAR' },
];
const plan = buildRenamePlan(rows);

describe('effectiveQuery', () => {
  it('returns the base statement unchanged with no transforms (v1)', () => {
    expect(effectiveQuery('SELECT * FROM t')).toBe('SELECT * FROM t');
  });
  it('composes transforms left to right', () => {
    const where: QueryTransform = {
      kind: 'where',
      apply: (sql) => `SELECT * FROM (${sql}) WHERE price > 0`,
    };
    expect(effectiveQuery('SELECT * FROM t', [where])).toBe(
      'SELECT * FROM (SELECT * FROM t) WHERE price > 0',
    );
  });
});

describe('countQuery', () => {
  it('wraps the effective query in count(*)', () => {
    expect(countQuery('SELECT * FROM t')).toBe(
      'SELECT count(*) AS n FROM (SELECT * FROM t) AS _buckaroo_count',
    );
  });
});

describe('windowedQuery', () => {
  it('applies LIMIT/OFFSET from start/end and defaults sort to index', () => {
    const sql = windowedQuery('SELECT * FROM t', plan, { start: 100, end: 200 });
    expect(sql).toContain('LIMIT 100 OFFSET 100');
    expect(sql).toContain('ORDER BY index ASC');
  });

  it('sorts by the renamed alias with an index tie-break', () => {
    const sql = windowedQuery('SELECT * FROM t', plan, {
      start: 0,
      end: 50,
      sort: 'a',
      sort_direction: 'desc',
    });
    expect(sql).toContain('ORDER BY a DESC, index ASC');
    expect(sql).toContain('LIMIT 50 OFFSET 0');
  });

  it('ignores an unknown sort column and falls back to index', () => {
    const sql = windowedQuery('SELECT * FROM t', plan, {
      start: 0,
      end: 10,
      sort: 'zzz',
    });
    expect(sql).toContain('ORDER BY index ASC');
  });

  it('clamps negative/empty windows to zero', () => {
    const sql = windowedQuery('SELECT * FROM t', plan, { start: 5, end: 5 });
    expect(sql).toContain('LIMIT 0 OFFSET 5');
  });
});
