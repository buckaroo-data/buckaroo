import { useState, useEffect, useRef } from 'react';
import { DFData, DFDataOrPayload } from './DFWhole';
import { resolveDFData, resolveDFDataAsync } from './resolveDFData';

/**
 * React hook that resolves all parquet_b64 values in a df_data_dict.
 *
 * On first render, attempts the synchronous resolveDFData for each value.
 * If any value returns [] (async parquetRead didn't fire yet), kicks off
 * an async decode and re-renders when complete.
 *
 * Returns a dict where all values are plain DFData arrays.
 */
export function useResolvedDFDataDict(
    dict: Record<string, DFDataOrPayload> | undefined | null
): Record<string, DFData> {
    // Try synchronous resolution first (works if data is already plain arrays or cached)
    const syncResult: Record<string, DFData> = {};
    let needsAsync = false;
    if (dict) {
        for (const [key, val] of Object.entries(dict)) {
            const resolved = resolveDFData(val);
            syncResult[key] = resolved;
            // If the input was parquet_b64 but sync returned [], we need async
            if (
                resolved.length === 0 &&
                val !== null &&
                val !== undefined &&
                !Array.isArray(val) &&
                typeof val === 'object' &&
                (val as any).format === 'parquet_b64'
            ) {
                needsAsync = true;
            }
        }
    }

    const [asyncResult, setAsyncResult] = useState<Record<string, DFData> | null>(null);

    // Track the dict identity to avoid stale updates
    const dictRef = useRef(dict);
    dictRef.current = dict;

    useEffect(() => {
        if (!needsAsync || !dict) return;
        let cancelled = false;

        const resolveAll = async () => {
            const result: Record<string, DFData> = {};
            for (const [key, val] of Object.entries(dict)) {
                result[key] = await resolveDFDataAsync(val);
            }
            if (!cancelled && dictRef.current === dict) {
                setAsyncResult(result);
            }
        };
        resolveAll();
        return () => { cancelled = true; };
    }, [dict, needsAsync]);

    return asyncResult ?? syncResult;
}
