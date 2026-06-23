/**
 * Search: turn a user search term into the `+ WHERE` transform the
 * effective-query seam (query.ts) reserves.
 *
 * Mirrors buckaroo's pandas `Search` command (customizations/pandas_commands.py):
 * a case-sensitive substring match (`Series.str.find` → DuckDB `contains`) over
 * every text column, OR-ed together, keeping any row that matches in at least
 * one column. The term is also surfaced to the viewer as `highlight_phrase` so
 * the string displayer highlights the match (backend.ts).
 */

import { quoteIdent } from './rename.js';
import { duckTypeToColType } from './duckTypes.js';

/**
 * Textual columns are the search targets. `duckTypeToColType` folds BOOLEAN
 * into `string`, but a boolean column is not text — exclude it so search
 * matches the pandas string/object semantics rather than matching 'true'.
 */
export function isSearchableType(duckType: string): boolean {
  if (duckTypeToColType(duckType) !== 'string') return false;
  const base = duckType.trim().toUpperCase().replace(/\(.*$/, '').trim();
  return base !== 'BOOLEAN' && base !== 'BOOL';
}

/** A no-op term — empty or whitespace — means "no filter". */
export function isActiveSearch(term: string | null | undefined): boolean {
  return typeof term === 'string' && term.length > 0;
}

/**
 * Build the search `QueryTransform`. `columns` are the original (pre-rename)
 * text column names; the transform wraps the effective SQL in a `WHERE` that
 * keeps rows where any column contains the term. An empty term or no columns
 * makes `apply` a no-op so the seam composes cleanly either way.
 */
export function buildSearchTransform(columns: string[], term: string) {
  const needle = term.replace(/'/g, "''");
  return {
    kind: 'search',
    apply(sql: string): string {
      if (!isActiveSearch(term) || columns.length === 0) return sql;
      const preds = columns
        .map((c) => `contains(CAST(${quoteIdent(c)} AS VARCHAR), '${needle}')`)
        .join(' OR ');
      return `SELECT * FROM (${sql}) AS _search WHERE (${preds})`;
    },
  };
}
