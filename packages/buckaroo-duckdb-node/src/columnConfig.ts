/**
 * Build the `df_viewer_config` (column_config + pinned_rows + left_col_configs)
 * from the rename plan.
 *
 * Pinned rows reference only the v1 stats this backend actually computes from
 * `SUMMARIZE` (see stats.ts) so no pinned row renders empty. Histogram rows are
 * a fast-follow once the histogram SQL lands.
 */

import type { RenamePlan } from './rename.js';
import { INDEX_COL } from './rename.js';
import { duckTypeToColType, displayerForColType } from './duckTypes.js';
import type { ColumnConfig, DFViewerConfig, PinnedRowConfig } from './wireTypes.js';

/**
 * The stat keys pinned in v1, in display order. Each must match a stat name
 * produced by stats.ts (and therefore a wide `{col}__{stat}` column).
 * `dtype` renders via `obj`; the rest `inherit` the column's own displayer
 * (styling_helpers.py: obj_/inherit_).
 */
export const V1_PINNED_STATS: ReadonlyArray<{ stat: string; inherit: boolean }> = [
  { stat: 'dtype', inherit: false },
  { stat: 'null_count', inherit: true },
  { stat: 'distinct_count', inherit: true },
  { stat: 'mean', inherit: true },
  { stat: 'std', inherit: true },
  { stat: 'min', inherit: true },
  { stat: 'q25', inherit: true },
  { stat: 'q50', inherit: true },
  { stat: 'q75', inherit: true },
  { stat: 'max', inherit: true },
];

export function buildPinnedRows(): PinnedRowConfig[] {
  return V1_PINNED_STATS.map(({ stat, inherit }) => ({
    primary_key_val: stat,
    displayer_args: inherit ? { displayer: 'inherit' } : { displayer: 'obj' },
  }));
}

export function buildColumnConfig(plan: RenamePlan): ColumnConfig[] {
  return plan.columns.map((c) => {
    const colType = duckTypeToColType(c.type);
    const cc: ColumnConfig = {
      col_name: c.alias,
      header_name: c.origName,
      displayer_args: displayerForColType(colType),
    };
    if (colType === 'string') {
      // DefaultMainStyling attaches a simple tooltip to string columns.
      cc.tooltip_config = { tooltip_type: 'simple', val_column: c.alias };
    }
    return cc;
  });
}

/** The leftmost (index) column config. */
export function buildLeftColConfigs(): ColumnConfig[] {
  return [
    {
      col_name: INDEX_COL,
      header_name: INDEX_COL,
      displayer_args: { displayer: 'obj' },
    },
  ];
}

export function buildDfViewerConfig(plan: RenamePlan): DFViewerConfig {
  return {
    pinned_rows: buildPinnedRows(),
    column_config: buildColumnConfig(plan),
    left_col_configs: buildLeftColConfigs(),
  };
}
