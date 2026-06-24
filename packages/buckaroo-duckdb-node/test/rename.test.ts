import { describe, it, expect } from 'vitest';
import { colAlias, quoteIdent, buildRenamePlan, INDEX_COL } from '../src/rename';
import type { DescribeRow } from '../src/DuckSource';

describe('colAlias (base-26, matches df_util.py:to_chars)', () => {
  it('maps 0..25 to a..z', () => {
    expect(colAlias(0)).toBe('a');
    expect(colAlias(1)).toBe('b');
    expect(colAlias(25)).toBe('z');
  });
  it('rolls over with a as the zero digit', () => {
    expect(colAlias(26)).toBe('ba');
    expect(colAlias(27)).toBe('bb');
    expect(colAlias(51)).toBe('bz');
    expect(colAlias(52)).toBe('ca');
  });
});

describe('quoteIdent', () => {
  it('quotes and doubles embedded quotes', () => {
    expect(quoteIdent('price')).toBe('"price"');
    expect(quoteIdent('price.usd')).toBe('"price.usd"');
    expect(quoteIdent('we"ird')).toBe('"we""ird"');
  });
});

describe('buildRenamePlan', () => {
  const rows: DescribeRow[] = [
    { name: 'price.usd', type: 'DOUBLE' },
    { name: 'index', type: 'BIGINT' },
    { name: 'name', type: 'VARCHAR' },
  ];
  const plan = buildRenamePlan(rows);

  it('renames every column to a,b,c and keeps the original-name map', () => {
    expect(plan.aliases).toEqual(['a', 'b', 'c']);
    expect(plan.renameMap).toEqual({ a: 'price.usd', b: 'index', c: 'name' });
  });

  it('carries dtype alongside each alias', () => {
    expect(plan.columns).toEqual([
      { alias: 'a', origName: 'price.usd', type: 'DOUBLE' },
      { alias: 'b', origName: 'index', type: 'BIGINT' },
      { alias: 'c', origName: 'name', type: 'VARCHAR' },
    ]);
  });

  it('a user column named index does not collide with the synthesized index', () => {
    const sql = plan.renamedRelation('SELECT 1');
    // the user's "index" column became alias b; our synthesized index is separate
    expect(sql).toContain('"index" AS b');
    expect(sql).toContain(`AS ${INDEX_COL}`);
  });

  it('projects aliases, synthesizes a 0-based index, and quotes dotted names', () => {
    const sql = plan.renamedRelation('SELECT * FROM t');
    expect(sql).toContain('"price.usd" AS a');
    expect(sql).toContain('(ROW_NUMBER() OVER ()) - 1 AS index');
    expect(sql).toContain('FROM (SELECT * FROM t) AS _buckaroo_src');
  });

  it('statsRelation nulls non-finite floats but leaves other types untouched', () => {
    const sql = plan.statsRelation('SELECT * FROM t');
    // the DOUBLE column (alias a) is guarded against nan/±inf
    expect(sql).toContain('CASE WHEN isfinite(a) THEN a ELSE NULL END AS a');
    // BIGINT (b), VARCHAR (c), and the synthesized index pass through bare
    expect(sql).not.toContain('isfinite(b)');
    expect(sql).not.toContain('isfinite(c)');
    expect(sql).toContain(`${INDEX_COL} FROM`);
    // it wraps the renamed relation (so SUMMARIZE sees the aliased columns)
    expect(sql).toContain('_buckaroo_src');
  });

  it('statsRelation does not guard DECIMAL (fixed-point cannot be non-finite)', () => {
    const decPlan = buildRenamePlan([{ name: 'pnl', type: 'DECIMAL(12,4)' }]);
    const sql = decPlan.statsRelation('SELECT * FROM t');
    expect(sql).not.toContain('isfinite');
  });
});
