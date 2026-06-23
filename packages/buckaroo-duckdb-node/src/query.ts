/**
 * SQL translation: the effective-query seam plus `infinite_request` windowing.
 *
 * Everything routes through `effectiveQuery(baseStmt, transforms)` — never off
 * the raw `stmt`. v1's transform list is empty (sort/paging are per-request
 * window params, not transforms), but routing `DESCRIBE`, stats and row
 * windowing through this one seam is what makes search (`+ WHERE`, re-run stats
 * for `search_` keys) and shape-changing quick commands clean fast-follows
 * rather than rewrites.
 */

import type { RenamePlan } from './rename';
import { INDEX_COL } from './rename';

/**
 * A transform applied to the base statement before describe/stats/rows. v1
 * defines none; the shape is fixed now so fast-follows (search WHERE, quick
 * commands) slot in without changing call sites.
 */
export interface QueryTransform {
  kind: string;
  /** wrap the incoming SQL and return the transformed SQL. */
  apply(sql: string): string;
}

/** Compose the base statement with the (v1: empty) transform list. */
export function effectiveQuery(
  baseStmt: string,
  transforms: QueryTransform[] = [],
): string {
  return transforms.reduce((sql, t) => t.apply(sql), baseStmt);
}

export interface WindowParams {
  start: number;
  end: number;
  /** renamed sort column (`a`), as it arrives from the client. */
  sort?: string;
  sort_direction?: string;
}

/** SELECT `count(*)` over the effective query — the `length` for infinite_resp. */
export function countQuery(effectiveSql: string): string {
  return `SELECT count(*) AS n FROM (${effectiveSql}) AS _buckaroo_count`;
}

/**
 * Build the windowed, sorted, renamed query for one `infinite_request`.
 *
 * Order of operations matters: the rename plan synthesizes `index` over the
 * unsorted relation, so we wrap *that* in the ORDER BY / LIMIT / OFFSET. Each
 * row therefore keeps its original `index` after sorting.
 *
 * The sort column arrives already renamed (`a`); we ORDER BY the alias directly
 * against the renamed relation. An unknown/empty sort falls back to `index` for
 * a stable window (DuckDB `ROW_NUMBER() OVER ()` order is otherwise unstable
 * across LIMIT/OFFSET calls).
 */
export function windowedQuery(
  effectiveSql: string,
  plan: RenamePlan,
  win: WindowParams,
): string {
  const inner = plan.renamedRelation(effectiveSql);
  const limit = Math.max(0, win.end - win.start);
  const offset = Math.max(0, win.start);

  const orderCol =
    win.sort && plan.aliases.includes(win.sort) ? win.sort : INDEX_COL;
  const dir = win.sort_direction === 'desc' ? 'DESC' : 'ASC';
  // tie-break on index so the window is deterministic when the sort col has ties
  const orderBy =
    orderCol === INDEX_COL
      ? `${INDEX_COL} ${dir}`
      : `${orderCol} ${dir}, ${INDEX_COL} ASC`;

  return `SELECT * FROM (${inner}) AS _buckaroo_win ORDER BY ${orderBy} LIMIT ${limit} OFFSET ${offset}`;
}
