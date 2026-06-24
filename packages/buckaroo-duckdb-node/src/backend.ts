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
import { computeHistograms } from './histogramSql.js';
import { buildSearchTransform, isSearchableType, isActiveSearch } from './search.js';
import type {
  BuckarooOptions,
  BuckarooState,
  DFEnvelope,
  DFViewerConfig,
  InitialStateMessage,
  PayloadArgs,
  PayloadResponse,
} from './wireTypes.js';

export interface DuckBackendOptions {
  /** summary-stats key. Defaults to `'all_stats'`. */
  summaryStatsKey?: string;
  /** Static transforms applied before search; reserved for quick commands. */
  transforms?: QueryTransform[];
  /** Initial search term. Usually set later via `setSearch` on a state change. */
  search?: string;
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
  /** Unfiltered row count — `df_meta.total_rows`. Stable across searches. */
  private totalRows = 0;
  /** Unfiltered count, cached so repeated searches don't re-summarize the base. */
  private cachedTotal?: number;
  /**
   * Rows after search — `df_meta.filtered_rows` and the infinite_resp `length`.
   * Cached against the current `searchTerm`; `setSearch` invalidates it so a row
   * window can never report a stale count. `undefined` means "not yet computed".
   */
  private cachedFiltered?: number;
  private searchTerm: string;

  constructor(source: DuckSource, baseStmt: string, opts: DuckBackendOptions = {}) {
    this.source = source;
    this.baseStmt = baseStmt;
    this.summaryStatsKey = opts.summaryStatsKey ?? 'all_stats';
    this.transforms = opts.transforms ?? [];
    this.searchTerm = opts.search ?? '';
  }

  /** The base effective SQL, search excluded. */
  private get effectiveSql(): string {
    return effectiveQuery(this.baseStmt, this.transforms);
  }

  /**
   * Set (or clear) the search term. Invalidates the cached filtered count so the
   * next `initialState`/`infinite_request` recomputes against the new term; an
   * empty term clears the filter. The active SQL is derived on demand (no cached
   * copy to go stale), so a row window is consistent regardless of call order.
   */
  setSearch(term: string): void {
    const next = term ?? '';
    if (next !== this.searchTerm) {
      this.searchTerm = next;
      this.cachedFiltered = undefined;
    }
  }

  /** The original (pre-rename) text columns search targets. */
  private searchColumns(plan: RenamePlan): string[] {
    return plan.columns.filter((c) => isSearchableType(c.type)).map((c) => c.origName);
  }

  /** Effective SQL with the search `+ WHERE` folded in (base SQL when inactive). */
  private searchEffectiveSql(plan: RenamePlan): string {
    if (!isActiveSearch(this.searchTerm)) return this.effectiveSql;
    const transform = buildSearchTransform(this.searchColumns(plan), this.searchTerm);
    return effectiveQuery(this.baseStmt, [...this.transforms, transform]);
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
    const active = isActiveSearch(this.searchTerm) && this.searchColumns(plan).length > 0;

    // Stats over the stats-safe (non-finite floats nulled so SUMMARIZE's
    // STDDEV_SAMP doesn't overflow), possibly search-filtered relation — pandas
    // re-runs summary stats on the filtered df, so we do too. The relation
    // includes the synthesized, non-null `index` column, so its SUMMARIZE count
    // is the row count of that set (filtered under search), no extra count
    // query needed. Seed the filtered-count cache from this same SUMMARIZE so a
    // following `infinite_request` doesn't re-run it.
    const summarizeRows = await this.source.summarize(plan.statsRelation(this.searchEffectiveSql(plan)));
    const indexRow = summarizeRows.find((r) => r.column_name === INDEX_COL);
    const filteredRows = indexRow ? Number(indexRow.count) : 0;
    this.cachedFiltered = filteredRows;

    // total_rows is the unfiltered count and never changes with search. Cache it
    // so repeated searches don't re-summarize the base relation; when search is
    // inactive the filtered count IS the total.
    if (!active) {
      this.cachedTotal = filteredRows;
    } else if (this.cachedTotal === undefined) {
      const baseRows = await this.source.summarize(plan.renamedRelation(this.effectiveSql));
      const baseIndex = baseRows.find((r) => r.column_name === INDEX_COL);
      this.cachedTotal = baseIndex ? Number(baseIndex.count) : filteredRows;
    }
    this.totalRows = this.cachedTotal ?? filteredRows;

    const sd = summarizeToSDType(summarizeRows);
    const statRows = sdTypeToStatRows(sd);

    // The histogram bars are a per-column list of objects, not a scalar stat,
    // so they ride as their own pinned row (injected right after dtype, the
    // position the `histogram` pin in columnConfig expects) rather than through
    // the SDType pivot.
    const histos = await computeHistograms(
      this.source,
      plan.renamedRelation(this.effectiveSql),
      plan,
      sd,
      this.totalRows,
    );
    statRows.splice(1, 0, { [INDEX_COL]: 'histogram', level_0: 'histogram', ...histos });

    const dfViewerConfig = buildDfViewerConfig(plan);
    if (active) this.applyHighlight(dfViewerConfig, this.searchTerm);

    return {
      type: 'initial_state',
      df_meta: {
        total_rows: this.totalRows,
        columns: plan.columns.length,
        filtered_rows: filteredRows,
        rows_shown: filteredRows,
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
      // Echo the active search term back in buckaroo_state. The StatusBar's
      // search cell is controlled by quick_command_args.search; if we returned
      // the bare READONLY_STATE (empty), its value would snap to '' while the
      // input still holds the term, and its debounce effect would resubmit the
      // search forever (a render-flicker loop). The Python path round-trips the
      // term the same way.
      buckaroo_state: isActiveSearch(this.searchTerm)
        ? { ...READONLY_STATE, quick_command_args: { search: [this.searchTerm] } }
        : READONLY_STATE,
      buckaroo_options: READONLY_OPTIONS,
    };
  }

  /**
   * Inject `highlight_phrase` into every string-column displayer so the matched
   * term is highlighted in the grid — the wire shape the Python `Search`
   * command produces via its SDResult `highlight_phrase` update.
   */
  private applyHighlight(cfg: DFViewerConfig, term: string): void {
    for (const cc of cfg.column_config) {
      if (cc.displayer_args.displayer === 'string') {
        cc.displayer_args = { ...cc.displayer_args, highlight_phrase: [term] };
      }
    }
  }

  /**
   * The filtered row count for the current search. Cached and invalidated by
   * `setSearch`, recomputed with one SUMMARIZE-count only when stale.
   * `initialState` seeds the cache from its own SUMMARIZE, so the common
   * state_change → initial_state → infinite_request flow never double-counts;
   * a standalone `setSearch` followed directly by `infinite_request` recomputes
   * here rather than reporting a stale length.
   */
  private async ensureFiltered(plan: RenamePlan): Promise<number> {
    if (this.cachedFiltered === undefined) {
      const rows = await this.source.summarize(plan.renamedRelation(this.searchEffectiveSql(plan)));
      const indexRow = rows.find((r) => r.column_name === INDEX_COL);
      this.cachedFiltered = indexRow ? Number(indexRow.count) : 0;
    }
    return this.cachedFiltered;
  }

  /**
   * Answer one `infinite_request`. The window runs against the active
   * (search-filtered) SQL — derived on demand from the current term, never a
   * cached copy that could go stale — serialized through the COPY→parquet
   * no-coercion path and returned inline as a `parquet_b64` envelope. `length`
   * is the filtered row count so the grid scrolls only the matching rows.
   */
  async handleInfiniteRequest(args: PayloadArgs): Promise<PayloadResponse> {
    const plan = await this.ensurePlan();
    const length = await this.ensureFiltered(plan);
    const sql = windowedQuery(this.searchEffectiveSql(plan), plan, {
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
      length,
      payload,
    };
  }
}
