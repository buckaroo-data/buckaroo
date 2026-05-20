import { DFData, DFDataOrPayload } from './DFWhole';
/**
 * Synchronously resolve a DFDataOrPayload to DFData.
 *
 * - If the input is already a plain DFData array, return it as-is.
 * - If it is a parquet-b64 payload, decode and parse the parquet into DFData.
 * - Falls back to an empty array on errors.
 *
 * NOTE: hyparquet's parquetRead onComplete may fire asynchronously in some
 * bundler environments (e.g. esbuild standalone). In such cases this function
 * returns [] and the result is cached when onComplete fires. Prefer
 * resolveDFDataAsync() for reliable decoding.
 */
export declare function resolveDFData(val: DFDataOrPayload | undefined | null): DFData;
/**
 * Asynchronously resolve a DFDataOrPayload to DFData.
 *
 * Unlike resolveDFData(), this properly awaits hyparquet's parquetRead
 * so it works reliably in all bundler environments.
 */
export declare function resolveDFDataAsync(val: DFDataOrPayload | undefined | null): Promise<DFData>;
/**
 * Pre-resolve all parquet_b64 values in a df_data_dict.
 *
 * Returns a new dict where parquet_b64 payloads have been decoded to DFData arrays.
 * This should be called before passing df_data_dict to React components so that
 * the synchronous resolveDFData() sees plain arrays and passes them through.
 */
export declare function preResolveDFDataDict(dict: Record<string, DFDataOrPayload> | undefined | null): Promise<Record<string, DFDataOrPayload>>;
