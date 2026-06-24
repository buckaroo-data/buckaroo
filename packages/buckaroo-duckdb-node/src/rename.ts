/**
 * Column renaming: raw DuckDB columns → buckaroo's `a, b, c…` space, plus a
 * synthesized `index`.
 *
 * Why rename at all (the JS core is agnostic to the `a,b,c` form, it only needs
 * `column_config.col_name` to equal the row-object keys) — three failure modes
 * that are *more* likely from user SQL than from a DataFrame:
 *   1. A column literally named `index`/`level_0` collides with buckaroo's
 *      reserved key (stat/pinned-row matching is by `{index: …}`). DuckDB has no
 *      implicit index so we synthesize one; renaming every user column out of
 *      the way removes the collision entirely.
 *   2. Dotted names (`price.usd`) are an ag-grid `field` foot-gun.
 *   3. Duplicate names from `SELECT * FROM a JOIN b` collapse to one JS key.
 *
 * The alias scheme is buckaroo's own (df_util.py:to_chars): base-26 with 'a' as
 * the zero digit — a, b, …, z, ba, bb, … — so this backend renames into the
 * exact same space the rest of buckaroo (e.g. xorq_buckaroo) uses.
 */

import type { DescribeRow } from './DuckSource.js';

/** Reserved row-object key buckaroo uses for stat/pinned-row matching. */
export const INDEX_COL = 'index';

/** df_util.py:to_digits — positive integer → base-`b` digits, most significant first. */
function toDigits(n: number, b: number): number[] {
  if (n === 0) return [0];
  const digits: number[] = [];
  while (n > 0) {
    digits.unshift(n % b);
    n = Math.floor(n / b);
  }
  return digits;
}

/** df_util.py:to_chars — column index → `a, b, …, z, ba, bb, …`. */
export function colAlias(i: number): string {
  return toDigits(i, 26)
    .map((d) => String.fromCharCode(d + 97))
    .join('');
}

/** Quote a SQL identifier, doubling embedded double-quotes. */
export function quoteIdent(name: string): string {
  return `"${name.replace(/"/g, '""')}"`;
}

/**
 * Real IEEE-754 floating types — the only ones that can hold `nan`/`±inf`.
 * DECIMAL/NUMERIC are fixed-point and cannot, so they're excluded from the
 * non-finite guard (`statsRelation`).
 */
const REAL_FLOAT_TYPES = new Set(['DOUBLE', 'REAL', 'FLOAT', 'FLOAT4', 'FLOAT8']);

function isRealFloatType(duckType: string): boolean {
  return REAL_FLOAT_TYPES.has(duckType.trim().toUpperCase().replace(/\(.*$/, '').trim());
}

export interface RenamePlan {
  /** alias (`a`) → original column name. For `header_name` + sort reversal. */
  renameMap: Record<string, string>;
  /** aliases in select order. */
  aliases: string[];
  /** the (alias, original DuckDB type) pairs in order. */
  columns: Array<{ alias: string; origName: string; type: string }>;
  /**
   * The renamed relation: every source column projected to its alias, plus a
   * synthesized 0-based `index` assigned in input-scan order (before any sort).
   * Callers wrap this with ORDER BY / LIMIT / OFFSET.
   */
  renamedRelation(stmt: string): string;
  /**
   * The stats-only relation: `renamedRelation` with non-finite floats
   * (`nan`/`±inf`) replaced by NULL. DuckDB's `SUMMARIZE` runs `STDDEV_SAMP`,
   * which overflows ("out of range") on a non-finite value and aborts the whole
   * stats query — so for summary statistics those values are treated as missing.
   * Only this path is guarded; the row (COPY) and histogram paths keep every
   * value (no coercion).
   */
  statsRelation(stmt: string): string;
}

/**
 * Build the rename plan from `DESCRIBE (<stmt>)` output.
 *
 * `index` is computed with `(ROW_NUMBER() OVER ()) - 1` over the *unsorted*
 * relation so each row keeps its original position when a sort is applied
 * downstream (the outer ORDER BY sorts rows that already carry their index).
 */
export function buildRenamePlan(describeRows: DescribeRow[]): RenamePlan {
  const columns = describeRows.map((row, i) => ({
    alias: colAlias(i),
    origName: row.name,
    type: row.type,
  }));

  const renameMap: Record<string, string> = {};
  for (const c of columns) renameMap[c.alias] = c.origName;
  const aliases = columns.map((c) => c.alias);

  const renamedRelation = (stmt: string): string => {
    const projections = columns.map(
      (c) => `${quoteIdent(c.origName)} AS ${c.alias}`,
    );
    projections.push(`(ROW_NUMBER() OVER ()) - 1 AS ${INDEX_COL}`);
    return `SELECT ${projections.join(', ')} FROM (${stmt}) AS _buckaroo_src`;
  };

  const statsRelation = (stmt: string): string => {
    const projections = columns.map((c) =>
      isRealFloatType(c.type)
        ? `CASE WHEN isfinite(${c.alias}) THEN ${c.alias} ELSE NULL END AS ${c.alias}`
        : c.alias,
    );
    projections.push(INDEX_COL);
    return `SELECT ${projections.join(', ')} FROM (${renamedRelation(stmt)}) AS _buckaroo_renamed`;
  };

  return { renameMap, aliases, columns, renamedRelation, statsRelation };
}
