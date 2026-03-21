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
 * Pivot a wide single-row parquet result (col__stat columns) back to
 * row-based DFData that downstream consumers expect.
 *
 * Input: single row object like {a__mean: 42, a__dtype: "float64", b__mean: 10, ...}
 * Output: DFData rows like [{index: "mean", level_0: "mean", a: 42, b: 10}, ...]
 */
export function pivotWideSummaryStats(wideRow: Record<string, any>): DFData {
    // Group values by stat name: stat -> {col -> value}
    const statCols: Record<string, Record<string, any>> = {};
    const allCols = new Set<string>();

    for (const [key, rawVal] of Object.entries(wideRow)) {
        const sepIdx = key.indexOf('__');
        if (sepIdx === -1) continue;
        const col = key.substring(0, sepIdx);
        const stat = key.substring(sepIdx + 2);
        allCols.add(col);
        if (!statCols[stat]) statCols[stat] = {};

        let val: any = rawVal;
        // JSON-parse all string values (cells are JSON-encoded in parquet)
        if (typeof val === 'string') {
            try {
                val = JSON.parse(val);
            } catch {
                // not JSON, keep as string
            }
        }
        // BigInt conversion (hyparquet INT64)
        if (typeof val === 'bigint') {
            const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);
            statCols[stat][col] = val >= -MAX_SAFE && val <= MAX_SAFE
                ? Number(val) : String(val);
            continue;
        }
        statCols[stat][col] = val;
    }

    // Build DFData: one row per stat
    const colList = Array.from(allCols);
    const rows: DFData = [];
    for (const [stat, cols] of Object.entries(statCols)) {
        const row: DFDataRow = { index: stat, level_0: stat };
        for (let i = 0; i < colList.length; i++) {
            const col = colList[i];
            row[col] = cols[col] ?? null;
        }
        rows.push(row);
    }
    return rows;
}

/**
 * JSON-parse each cell value in a row from parquet-decoded data.
 *
 * For non-wide parquet data (e.g. main DataFrame), object/category columns
 * are JSON-encoded on the Python side and need to be parsed back.
 * The 'index' and 'level_0' columns are kept as-is.
 */
function parseParquetRow(row: Record<string, any>): DFDataRow {
    const parsed: DFDataRow = {};
    for (const [key, val] of Object.entries(row)) {
        if (key === 'index' || key === 'level_0') {
            parsed[key] = typeof val === 'bigint' ? Number(val) : val;
        } else if (typeof val === 'string') {
            try {
                parsed[key] = JSON.parse(val);
            } catch {
                parsed[key] = val;
            }
        } else if (typeof val === 'bigint') {
            const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);
            parsed[key] = val >= -MAX_SAFE && val <= MAX_SAFE
                ? Number(val) : String(val);
        } else {
            parsed[key] = val;
        }
    }
    return parsed;
}

/**
 * Detect wide-column format: single row where column names contain '__'.
 */
function isWideFormat(rows: any[]): boolean {
    if (rows.length !== 1) return false;
    const keys = Object.keys(rows[0]);
    return keys.some(k => k.indexOf('__') !== -1);
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
                    if (isWideFormat(data)) {
                        result = pivotWideSummaryStats(data[0] as Record<string, any>);
                    } else {
                        result = (data as DFDataRow[]).map(parseParquetRow);
                    }
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
            let result: DFData;
            if (isWideFormat(data)) {
                result = pivotWideSummaryStats(data[0] as Record<string, any>);
            } else {
                result = data as DFData;
            }
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
