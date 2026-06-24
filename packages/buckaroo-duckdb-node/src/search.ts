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

/**
 * An empty/absent term means "no filter". Whitespace is a real term — pandas
 * `Search` no-ops only on `""` (`val == ""`), so we must not trim here.
 */
export function isActiveSearch(term: string | null | undefined): boolean {
  return typeof term === 'string' && term.length > 0;
}

/**
 * Build the search `QueryTransform`. `columns` are the original (pre-rename)
 * text column names; the transform wraps the effective SQL in a `WHERE` that
 * keeps rows where any column contains the term. An empty term makes `apply` a
 * no-op; an active term with no text columns matches nothing (an always-false
 * filter), mirroring pandas `search_df_str` (all-false mask OR-ed over zero
 * string columns → empty frame) rather than passing every row through.
 */
export function buildSearchTransform(columns: string[], term: string) {
  const needle = term.replace(/'/g, "''");
  return {
    kind: 'search',
    apply(sql: string): string {
      if (!isActiveSearch(term)) return sql;
      if (columns.length === 0) {
        return `SELECT * FROM (${sql}) AS _search WHERE (1=0)`;
      }
      const preds = columns
        .map((c) => `contains(CAST(${quoteIdent(c)} AS VARCHAR), '${needle}')`)
        .join(' OR ');
      return `SELECT * FROM (${sql}) AS _search WHERE (${preds})`;
    },
  };
}
