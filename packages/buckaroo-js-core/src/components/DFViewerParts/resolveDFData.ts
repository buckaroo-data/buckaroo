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
 * Convert a hyparquet BigInt cell to Number when safe, stringify otherwise.
 * hyparquet decodes parquet INT64 as JS BigInt; using Number when it fits
 * keeps downstream code BigInt-unaware, and stringifying preserves precision
 * for the rare out-of-range case (fixes #627).
 */
function bigintToCell(val: bigint): number | string {
    const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);
    return val >= -MAX_SAFE && val <= MAX_SAFE ? Number(val) : String(val);
}

/**
 * JSON-parse each cell value in a row from row-layout parquet data.
 *
 * For non-wide payloads (the main DataFrame artifact), object/category
 * columns are JSON-encoded on the Python side and must be parsed back.
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
            parsed[key] = bigintToCell(val);
        } else {
            parsed[key] = val;
        }
    }
    return parsed;
}

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
export function pivotWideSummaryStats(wideRow: Record<string, any>): DFData {
    // stat -> col -> value
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
        if (typeof val === 'bigint') {
            val = bigintToCell(val);
        } else if (typeof val === 'string') {
            try {
                val = JSON.parse(val);
            } catch {
                // Not valid JSON — keep raw. Should not happen for values
                // produced by _stat_value_to_pa_array, but guard anyway so
                // a corrupt cell doesn't take the whole pivot down.
            }
        }
        statCols[stat][col] = val;
    }

    const colList = Array.from(allCols);
    const rows: DFData = [];
    for (const [stat, cols] of Object.entries(statCols)) {
        // level_0 is duplicated alongside index for legacy row-format parity;
        // a future cleanup can drop level_0 once consumers stop reading it.
        const row: DFDataRow = { index: stat, level_0: stat };
        for (const col of colList) {
            row[col] = cols[col] ?? null;
        }
        rows.push(row);
    }
    return rows;
}

function isWideFormat(payload: ParquetB64Payload): boolean {
    return payload.layout === 'wide';
}

function decodeParquetRows(
    payload: ParquetB64Payload,
    rows: Record<string, any>[],
): DFData {
    if (isWideFormat(payload)) {
        // Wide layout always serializes a single row.
        return rows.length === 0 ? [] : pivotWideSummaryStats(rows[0]);
    }
    return (rows as DFDataRow[]).map(parseParquetRow);
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
                    result = decodeParquetRows(val, data);
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
            const result = decodeParquetRows(val, data);
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
