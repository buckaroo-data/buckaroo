import { DFData, DFDataOrPayload } from './DFWhole';
/**
 * Pivot a wide single-row parquet result (col__stat columns) back to the
 * row-based DFData shape that downstream consumers expect.
 *
 * Input: one row like ``{a__mean: 42, a__dtype: '"float64"', b__mean: 10, ...}``
 * Output: ``[{index: 'mean', level_0: 'mean', a: 42, b: 10}, ...]``
 *
 * Encoding contract (mirrors ``_stat_value_to_pa_array`` in serialization_utils.py):
 *   - numbers/bools/null arrive as native JS types and pass through
 *   - BigInt cells (parquet INT64) are safe-converted
 *   - strings are JSON.parsed unconditionally: the Python side always
 *     JSON-encodes str/list/dict, so a plain string `"float64"` arrives
 *     as the literal `"\"float64\""` and parses back to `"float64"`
 */
export declare function pivotWideSummaryStats(wideRow: Record<string, any>): DFData;
/**
 * The one place that owns "how a dataframe payload is decoded".
 *
 * Consumes a transport envelope (or a plain pre-decoded DFData array, which
 * passes through) and returns DFData. Awaited only at the ingestion edges —
 * the comm/ws message handler, the df_data_dict trait hook, and the static
 * mount — so the component tree stays synchronous on plain DFData.
 *
 * Branches:
 *   - null/undefined  → []
 *   - DFData array    → passthrough
 *   - parquet_buffer  → bytes from buffers[buffer_index] → rows
 *   - parquet_b64     → atob → bytes → rows (cached by the b64 string)
 *   - json            → inline record array
 * then for parquet-derived rows: layout 'wide' pivots, else parseParquetRow.
 */
export declare function decodeDFData(env: DFDataOrPayload | null | undefined, buffers?: DataView[]): Promise<DFData>;
/**
 * Decode every envelope value in a df_data_dict to DFData. Plain-array values
 * pass through. Used by the df_data_dict ingestion edge so the component tree
 * receives decoded data end-to-end.
 */
export declare function decodeDFDataDict(dict: Record<string, DFDataOrPayload> | undefined | null, buffers?: DataView[]): Promise<Record<string, DFData>>;
