/**
 * Wire-contract types for the buckaroo viewer protocol.
 *
 * These mirror the structural shapes that `buckaroo-js-core` already speaks.
 * buckaroo-js-core does not export its config/data types from its public entry
 * (only `IModel` is exported), so this backend re-declares the protocol it
 * produces. They are structurally compatible by design — the citations below
 * point at the source of truth in buckaroo-js-core; keep them in sync.
 *
 * Source of truth:
 *   - components/DFViewerParts/DFWhole.ts  (DisplayerArgs, ColumnConfig, DFData, DFEnvelope)
 *   - components/DFViewerParts/gridUtils.ts (IDisplayArgs)
 *   - components/DFViewerParts/SmartRowCache.ts (PayloadArgs)
 *   - components/WidgetTypes.tsx (DFMeta, BuckarooState, BuckarooOptions)
 */

// ---------------------------------------------------------------------------
// Displayer args  (DFWhole.ts:9-108)
// ---------------------------------------------------------------------------

export interface ObjDisplayerA {
  displayer: 'obj';
  max_length?: number;
}

export interface StringDisplayerA {
  displayer: 'string';
  max_length?: number;
}

export interface FloatDisplayerA {
  displayer: 'float';
  min_fraction_digits: number;
  max_fraction_digits: number;
}

export interface IntegerDisplayerA {
  displayer: 'integer';
  min_digits: number;
  max_digits: number;
}

export interface DatetimeLocaleDisplayerA {
  displayer: 'datetimeLocaleString';
  locale: 'en-US' | 'en-GB' | 'en-CA' | 'fr-FR' | 'es-ES' | 'de-DE' | 'ja-JP';
  args: Record<string, unknown>;
}

export interface DatetimeDefaultDisplayerA {
  displayer: 'datetimeDefault';
}

export interface BooleanDisplayerA {
  displayer: 'boolean';
}

export interface HistogramDisplayerA {
  displayer: 'histogram';
}

/**
 * One bar of a `histogram` summary stat — the cell value the `displayer:
 * 'histogram'` pinned row renders. Mirrors buckaroo-js-core's `HistogramBar`
 * (HistogramCell.tsx). Exactly one of the value keys is set per bar; `name` is
 * always the bucket label. Percentages are on the 0–100 scale.
 */
export interface HistogramBar {
  name: string;
  /** numeric meat-bucket population % */
  population?: number;
  /** categorical top-N population % */
  cat_pop?: number;
  /** numeric low/high tail marker (always 1) */
  tail?: number;
  /** longtail bucket % */
  longtail?: number;
  /** unique-values bucket % */
  unique?: number;
  /** missing-values bucket % */
  NA?: number;
}

export interface InheritDisplayerA {
  displayer: 'inherit';
}

export type DisplayerArgs =
  | ObjDisplayerA
  | StringDisplayerA
  | FloatDisplayerA
  | IntegerDisplayerA
  | DatetimeLocaleDisplayerA
  | DatetimeDefaultDisplayerA
  | BooleanDisplayerA
  | HistogramDisplayerA
  | InheritDisplayerA;

// ---------------------------------------------------------------------------
// Column / viewer config  (DFWhole.ts:170-242, styling_core.py:143-178)
// ---------------------------------------------------------------------------

export interface TooltipConfig {
  tooltip_type: 'simple';
  val_column: string;
}

export interface NormalColumnConfig {
  col_name: string;
  header_name: string;
  displayer_args: DisplayerArgs;
  tooltip_config?: TooltipConfig;
  ag_grid_specs?: Record<string, unknown>;
}

export type ColumnConfig = NormalColumnConfig;

export interface PinnedRowConfig {
  primary_key_val: string;
  displayer_args: DisplayerArgs;
  default_renderer_columns?: string[];
}

export interface DFViewerConfig {
  pinned_rows: PinnedRowConfig[];
  column_config: ColumnConfig[];
  left_col_configs: ColumnConfig[];
  extra_grid_config?: Record<string, unknown>;
  component_config?: Record<string, unknown>;
}

/** gridUtils.ts:411-415 / styling_core.py:180-183 */
export interface IDisplayArgs {
  data_key: string;
  df_viewer_config: DFViewerConfig;
  summary_stats_key: string;
}

// ---------------------------------------------------------------------------
// Data + transport envelope
// ---------------------------------------------------------------------------

export type DFDataRow = Record<
  string,
  string | number | boolean | unknown[] | Record<string, unknown> | null
>;
export type DFData = DFDataRow[];

/**
 * Transport envelope — the unified `DFEnvelope` from #933 (DFWhole.ts:258-261,
 * docs/plans/unified-df-transport.md). js-core's
 * `decodeDFData(envelope, buffers)` is the matching consumer. The DuckDB
 * backend only ever emits `parquet_b64` (inline base64 parquet, the
 * no-coercion path) for rows and `json` for the pre-pivoted stats; the
 * `parquet_buffer` variant is declared so this type stays structurally
 * identical to the js-core source of truth.
 *
 * `layout` is orthogonal to transport: `'wide'` marks the single-row
 * `{col}__{stat}` summary-stats shape the decoder pivots; `'row'` (or absent)
 * is ordinary row-layout parquet, JSON-parsed per cell.
 */
export type DFEnvelope =
  | { format: 'parquet_buffer'; buffer_index: number; layout?: 'wide' | 'row' }
  | { format: 'parquet_b64'; data: string; layout?: 'wide' | 'row' }
  | { format: 'json'; data: DFData; layout?: 'wide' | 'row' };

// ---------------------------------------------------------------------------
// Widget state  (WidgetTypes.tsx)
// ---------------------------------------------------------------------------

export interface DFMeta {
  total_rows: number;
  columns: number;
  filtered_rows: number;
  rows_shown: number;
}

export interface BuckarooState {
  sampled: string | false;
  cleaning_method: string | false;
  quick_command_args: Record<string, (number | string)[]>;
  post_processing: string | false;
  df_display: string;
  show_commands: string | false;
}

export interface BuckarooOptions {
  sampled: string[];
  cleaning_method: string[];
  post_processing: string[];
  df_display: string[];
  show_commands: string[];
}

// ---------------------------------------------------------------------------
// Infinite-scroll request/response  (SmartRowCache.ts:17-33)
// ---------------------------------------------------------------------------

export interface PayloadArgs {
  sourceName: string;
  start: number;
  end: number;
  origEnd: number;
  sort?: string;
  sort_direction?: string;
  request_time?: number;
  second_request?: PayloadArgs;
}

/**
 * The `infinite_resp` message. Per #933 the parquet bytes ride in `payload` as
 * a bare `DFEnvelope` (decoded by `decodeDFData(msg.payload, buffers)`) rather
 * than via the untagged `buffers[0]` convention.
 */
export interface PayloadResponse {
  type: 'infinite_resp';
  key: PayloadArgs;
  length: number;
  payload: DFEnvelope;
  error_info?: string;
}

/** The `initial_state` message for a read-only viewer. */
export interface InitialStateMessage {
  type: 'initial_state';
  df_meta: DFMeta;
  df_data_dict: Record<string, DFEnvelope | DFData>;
  df_display_args: Record<string, IDisplayArgs>;
  buckaroo_state: BuckarooState;
  buckaroo_options: BuckarooOptions;
}
