/**
 * The transport-agnostic backend. Composes rename + query + stats + config into
 * the two messages a read-only viewer needs:
 *
 *   - `initialState()`     → the `initial_state` message.
 *   - `handleInfiniteRequest(args)` → the `infinite_resp` message for one window.
 *
 * It owns the buckaroo-specific logic aistudio should not reinvent: the
 * DESCRIBE→a,b,c+index rename, the SUMMARIZE→SDType stats, the
 * infinite_request→windowed-SQL translation, and the type→displayer config.
 *
 * It is deliberately ignorant of *how* messages reach the renderer — wrap it in
 * an IModel-over-IPC adapter (transport.ts) or any other transport.
 */

import type { DuckSource } from './DuckSource.js';
import { buildRenamePlan, INDEX_COL, type RenamePlan } from './rename.js';
import { effectiveQuery, windowedQuery, type QueryTransform } from './query.js';
import { buildDfViewerConfig } from './columnConfig.js';
import { summarizeToSDType, sdTypeToStatRows } from './stats.js';
import type {
  BuckarooOptions,
  BuckarooState,
  DFEnvelope,
  InitialStateMessage,
  PayloadArgs,
  PayloadResponse,
} from './wireTypes.js';

export interface DuckBackendOptions {
  /** summary-stats key. Defaults to `'all_stats'`. */
  summaryStatsKey?: string;
  /** v1: empty. Reserved for search (`+ WHERE`) and quick-command transforms. */
  transforms?: QueryTransform[];
}

/**
 * The live infinite source MUST be keyed `'main'`: the viewer
 * (`BuckarooWidgetInfinite.getDataWrapper`) only wires the on-demand datasource
 * when `data_key === 'main'`. Any other key is read as a preloaded static
 * array out of `df_data_dict`, which we leave empty — so the grid would render
 * empty and never issue `infinite_request`s. Not configurable for that reason.
 */
const MAIN_DATA_KEY = 'main';

const READONLY_STATE: BuckarooState = {
  sampled: false,
  cleaning_method: false,
  quick_command_args: {},
  post_processing: false,
  df_display: 'main',
  show_commands: false,
};

const READONLY_OPTIONS: BuckarooOptions = {
  sampled: [],
  cleaning_method: [],
  post_processing: [],
  df_display: ['main'],
  show_commands: [],
};

function toBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString('base64');
}

export class DuckBackend {
  private readonly source: DuckSource;
  private readonly baseStmt: string;
  private readonly summaryStatsKey: string;
  private readonly transforms: QueryTransform[];

  private plan?: RenamePlan;
  private totalRows = 0;

  constructor(source: DuckSource, baseStmt: string, opts: DuckBackendOptions = {}) {
    this.source = source;
    this.baseStmt = baseStmt;
    this.summaryStatsKey = opts.summaryStatsKey ?? 'all_stats';
    this.transforms = opts.transforms ?? [];
  }

  private get effectiveSql(): string {
    return effectiveQuery(this.baseStmt, this.transforms);
  }

  /** Describe the (renamed) relation and cache the rename plan. */
  private async ensurePlan(): Promise<RenamePlan> {
    if (!this.plan) {
      const describeRows = await this.source.describe(this.effectiveSql);
      this.plan = buildRenamePlan(describeRows);
    }
    return this.plan;
  }

  async initialState(): Promise<InitialStateMessage> {
    const plan = await this.ensurePlan();

    // Stats over the renamed relation; column names come back as aliases. The
    // relation includes the synthesized, non-null `index` column, so its
    // SUMMARIZE count is the total row count — no extra count query needed.
    const summarizeRows = await this.source.summarize(plan.renamedRelation(this.effectiveSql));
    const indexRow = summarizeRows.find((r) => r.column_name === INDEX_COL);
    this.totalRows = indexRow ? Number(indexRow.count) : 0;

    const sd = summarizeToSDType(summarizeRows);
    const statRows = sdTypeToStatRows(sd);

    const dfViewerConfig = buildDfViewerConfig(plan);

    return {
      type: 'initial_state',
      df_meta: {
        total_rows: this.totalRows,
        columns: plan.columns.length,
        filtered_rows: this.totalRows,
        rows_shown: this.totalRows,
      },
      df_data_dict: {
        // main rows arrive on demand via infinite_request
        [MAIN_DATA_KEY]: [],
        // stats are small scalar aggregates — emitted pre-pivoted as json
        [this.summaryStatsKey]: { format: 'json', data: statRows },
      },
      df_display_args: {
        main: {
          data_key: MAIN_DATA_KEY,
          df_viewer_config: dfViewerConfig,
          summary_stats_key: this.summaryStatsKey,
        },
      },
      buckaroo_state: READONLY_STATE,
      buckaroo_options: READONLY_OPTIONS,
    };
  }

  /**
   * Answer one `infinite_request`. The window is serialized through the
   * COPY→parquet no-coercion path and returned inline as a `parquet_b64`
   * envelope (single JSON message, no binary side-channel frame).
   */
  async handleInfiniteRequest(args: PayloadArgs): Promise<PayloadResponse> {
    const plan = await this.ensurePlan();
    const sql = windowedQuery(this.effectiveSql, plan, {
      start: args.start,
      end: args.end,
      sort: args.sort,
      sort_direction: args.sort_direction,
    });
    const bytes = await this.source.copyToParquet(sql);
    const payload: DFEnvelope = { format: 'parquet_b64', data: toBase64(bytes) };
    return {
      type: 'infinite_resp',
      key: args,
      length: this.totalRows,
      payload,
    };
  }
}
