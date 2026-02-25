import { parquetRead, parquetMetadata } from 'hyparquet';
import { DFData, DFDataRow, DFDataOrPayload, ParquetB64Payload } from './DFWhole';

/**
 * Type guard: returns true if the value is a parquet-b64 tagged payload.
 */
function isParquetB64(val: unknown): val is ParquetB64Payload {
    return (
        val !== null &&
        typeof val === 'object' &&
        !Array.isArray(val) &&
        (val as any).format === 'parquet_b64' &&
        typeof (val as any).data === 'string'
    );
}

// Simple LRU-ish cache keyed by the b64 string (reference equality would miss
// when the trait is re-serialised with the same content).
const _cache = new Map<string, DFData>();
const MAX_CACHE = 8;

function cacheSet(key: string, value: DFData) {
    if (_cache.size >= MAX_CACHE) {
        // evict oldest
        const first = _cache.keys().next().value;
        if (first !== undefined) _cache.delete(first);
    }
    _cache.set(key, value);
}

/**
 * Decode a base64 string to an ArrayBuffer.
 */
function b64ToArrayBuffer(b64: string): ArrayBuffer {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
        bytes[i] = bin.charCodeAt(i);
    }
    return bytes.buffer;
}

/**
 * JSON-parse each cell value in a row from parquet-decoded data.
 *
 * The Python side JSON-encodes every cell before writing to parquet
 * (because summary stats have mixed types per column). We need to
 * JSON.parse each value back to its original type.
 *
 * The 'index' column is left as a plain string (stat name like 'mean', 'dtype').
 */
function parseParquetRow(row: Record<string, any>): DFDataRow {
    const parsed: DFDataRow = {};
    for (const [key, val] of Object.entries(row)) {
        if (key === 'index' || key === 'level_0') {
            // index/level_0 columns are stat names — keep as-is
            // BigInt from hyparquet INT64 columns must be converted to Number
            parsed[key] = typeof val === 'bigint' ? Number(val) : val;
        } else if (typeof val === 'string') {
            try {
                parsed[key] = JSON.parse(val);
            } catch {
                parsed[key] = val;
            }
        } else if (typeof val === 'bigint') {
            // hyparquet decodes INT64 as BigInt; convert to Number for JSON compat
            parsed[key] = Number(val);
        } else {
            parsed[key] = val;
        }
    }
    return parsed;
}

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
export function resolveDFData(val: DFDataOrPayload | undefined | null): DFData {
    if (val === undefined || val === null) return [];
    if (Array.isArray(val)) return val as DFData;

    if (isParquetB64(val)) {
        // Check cache — only return cached if non-empty (async decode may have
        // cached [] before onComplete fired)
        const cached = _cache.get(val.data);
        if (cached && cached.length > 0) return cached;

        try {
            const buf = b64ToArrayBuffer(val.data);
            const metadata = parquetMetadata(buf);
            let result: DFData = [];
            parquetRead({
                file: buf,
                metadata,
                rowFormat: 'object',
                onComplete: (data: any[]) => {
                    // JSON-parse each cell to recover typed values
                    result = (data as DFDataRow[]).map(parseParquetRow);
                    cacheSet(val.data, result);
                },
            });
            // If synchronous (Jupyter/webpack), result is already populated
            if (result.length > 0) {
                cacheSet(val.data, result);
            }
            return result;
        } catch (e) {
            console.error('resolveDFData: failed to decode parquet_b64', e);
            return [];
        }
    }

    // Unknown format — treat as empty
    console.warn('resolveDFData: unknown payload format', val);
    return [];
}

/**
 * Asynchronously resolve a DFDataOrPayload to DFData.
 *
 * Unlike resolveDFData(), this properly awaits hyparquet's parquetRead
 * so it works reliably in all bundler environments.
 */
export async function resolveDFDataAsync(val: DFDataOrPayload | undefined | null): Promise<DFData> {
    if (val === undefined || val === null) return [];
    if (Array.isArray(val)) return val as DFData;

    if (isParquetB64(val)) {
        const cached = _cache.get(val.data);
        if (cached && cached.length > 0) return cached;

        try {
            const buf = b64ToArrayBuffer(val.data);
            const metadata = parquetMetadata(buf);
            const data = await new Promise<any[]>((resolve, reject) => {
                try {
                    parquetRead({
                        file: buf,
                        metadata,
                        rowFormat: 'object',
                        onComplete: (rows: any[]) => resolve(rows),
                    });
                } catch (e) {
                    reject(e);
                }
            });
            const result = (data as DFDataRow[]).map(parseParquetRow);
            cacheSet(val.data, result);
            return result;
        } catch (e) {
            console.error('resolveDFDataAsync: failed to decode parquet_b64', e);
            return [];
        }
    }

    console.warn('resolveDFDataAsync: unknown payload format', val);
    return [];
}

/**
 * Pre-resolve all parquet_b64 values in a df_data_dict.
 *
 * Returns a new dict where parquet_b64 payloads have been decoded to DFData arrays.
 * This should be called before passing df_data_dict to React components so that
 * the synchronous resolveDFData() sees plain arrays and passes them through.
 */
export async function preResolveDFDataDict(
    dict: Record<string, DFDataOrPayload> | undefined | null
): Promise<Record<string, DFDataOrPayload>> {
    if (!dict) return {};
    const result: Record<string, DFDataOrPayload> = {};
    const promises: Promise<void>[] = [];
    for (const [key, val] of Object.entries(dict)) {
        if (isParquetB64(val)) {
            promises.push(
                resolveDFDataAsync(val).then((resolved) => {
                    result[key] = resolved;
                })
            );
        } else {
            result[key] = val;
        }
    }
    await Promise.all(promises);
    return result;
}
