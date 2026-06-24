/**
 * Build the `df_viewer_config` (column_config + pinned_rows + left_col_configs)
 * from the rename plan.
 *
 * Pinned rows reference only stats this backend actually computes — the
 * `SUMMARIZE`-derived stats (see stats.ts) plus the `histogram` row the backend
 * injects — so no pinned row renders empty.
 */

import type { RenamePlan } from './rename.js';
import { INDEX_COL } from './rename.js';
import { duckTypeToColType, displayerForColType } from './duckTypes.js';
import type {
  ColumnConfig,
  DFViewerConfig,
  DisplayerArgs,
  PinnedRowConfig,
} from './wireTypes.js';

/**
 * The stat keys pinned in v1, in display order. `dtype` renders via `obj`,
 * `histogram` via the histogram displayer, and the rest `inherit` the column's
 * own displayer (styling_helpers.py: obj_/inherit_/pinned_histogram). The
 * histogram row sits right after dtype to match DefaultMainStyling.pinned_rows.
 */
export const V1_PINNED_STATS: ReadonlyArray<{ stat: string; displayer_args: DisplayerArgs }> = [
  { stat: 'dtype', displayer_args: { displayer: 'obj' } },
  { stat: 'histogram', displayer_args: { displayer: 'histogram' } },
  { stat: 'null_count', displayer_args: { displayer: 'inherit' } },
  { stat: 'distinct_count', displayer_args: { displayer: 'inherit' } },
  { stat: 'mean', displayer_args: { displayer: 'inherit' } },
  { stat: 'std', displayer_args: { displayer: 'inherit' } },
  { stat: 'min', displayer_args: { displayer: 'inherit' } },
  { stat: 'q25', displayer_args: { displayer: 'inherit' } },
  { stat: 'q50', displayer_args: { displayer: 'inherit' } },
  { stat: 'q75', displayer_args: { displayer: 'inherit' } },
  { stat: 'max', displayer_args: { displayer: 'inherit' } },
];

export function buildPinnedRows(): PinnedRowConfig[] {
  return V1_PINNED_STATS.map(({ stat, displayer_args }) => ({
    primary_key_val: stat,
    displayer_args,
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
