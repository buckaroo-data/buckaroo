import { DFData, DFDataOrPayload } from './DFWhole';
/**
 * React hook that resolves all parquet_b64 values in a df_data_dict.
 *
 * On first render, attempts the synchronous resolveDFData for each value.
 * If any value returns [] (async parquetRead didn't fire yet), kicks off
 * an async decode and re-renders when complete.
 *
 * Returns a dict where all values are plain DFData arrays.
 */
export declare function useResolvedDFDataDict(dict: Record<string, DFDataOrPayload> | undefined | null): Record<string, DFData>;
