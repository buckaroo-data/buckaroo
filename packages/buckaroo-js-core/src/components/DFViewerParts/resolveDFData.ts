import { parquetRead, parquetMetadata } from 'hyparquet';
import { DFData, DFDataRow, DFDataOrPayload, DFEnvelope } from './DFWhole';

// Simple LRU-ish cache keyed by the b64 string (reference equality would miss
// when the trait is re-serialised with the same content). Only the inline
// b64 path is cached — comm buffers are one-shot and have no stable key.
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
 * Extract the exact parquet bytes a comm side-channel buffer carries.
 *
 * anywidget / the WebSocket model hand each frame over as a DataView. Slice
 * to the view's window so a non-zero byteOffset (shared backing buffer)
 * doesn't feed stray bytes into hyparquet.
 */
function dataViewToArrayBuffer(dv: DataView): ArrayBuffer {
    return dv.buffer.slice(dv.byteOffset, dv.byteOffset + dv.byteLength);
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

/**
 * Turn raw hyparquet rows into DFData, honoring the envelope's layout.
 * 'wide' → pivot the single summary-stats row; otherwise JSON-parse each
 * object/list/dict cell back to its native value.
 */
function parquetRowsToDFData(rows: Record<string, any>[], layout?: string): DFData {
    if (layout === 'wide') {
        // Wide layout always serializes a single row.
        return rows.length === 0 ? [] : pivotWideSummaryStats(rows[0]);
    }
    return (rows as DFDataRow[]).map(parseParquetRow);
}

/**
 * Read parquet bytes into raw hyparquet rows. Awaits onComplete so it works
 * reliably across bundler environments (esbuild standalone fires async).
 */
async function readParquetRows(buf: ArrayBuffer): Promise<Record<string, any>[]> {
    const metadata = parquetMetadata(buf);
    return await new Promise<Record<string, any>[]>((resolve, reject) => {
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
}

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
export async function decodeDFData(
    env: DFDataOrPayload | null | undefined,
    buffers?: DataView[],
): Promise<DFData> {
    if (env === undefined || env === null) return [];
    if (Array.isArray(env)) return env as DFData;

    const envelope = env as DFEnvelope;
    try {
        if (envelope.format === 'json') {
            return (envelope.data ?? []) as DFData;
        }
        if (envelope.format === 'parquet_b64') {
            const cached = _cache.get(envelope.data);
            if (cached && cached.length > 0) return cached;
            const rows = await readParquetRows(b64ToArrayBuffer(envelope.data));
            const result = parquetRowsToDFData(rows, envelope.layout);
            cacheSet(envelope.data, result);
            return result;
        }
        if (envelope.format === 'parquet_buffer') {
            const dv = buffers?.[envelope.buffer_index];
            if (dv === undefined) {
                console.error(
                    'decodeDFData: parquet_buffer envelope but buffers[%d] is missing',
                    envelope.buffer_index,
                );
                return [];
            }
            const rows = await readParquetRows(dataViewToArrayBuffer(dv));
            return parquetRowsToDFData(rows, envelope.layout);
        }
    } catch (e) {
        console.error('decodeDFData: failed to decode envelope', envelope, e);
        return [];
    }

    console.warn('decodeDFData: unknown envelope format', env);
    return [];
}

/**
 * Decode every envelope value in a df_data_dict to DFData. Plain-array values
 * pass through. Used by the df_data_dict ingestion edge so the component tree
 * receives decoded data end-to-end.
 */
export async function decodeDFDataDict(
    dict: Record<string, DFDataOrPayload> | undefined | null,
    buffers?: DataView[],
): Promise<Record<string, DFData>> {
    if (!dict) return {};
    const result: Record<string, DFData> = {};
    const entries = Object.entries(dict);
    await Promise.all(
        entries.map(async ([key, val]) => {
            result[key] = await decodeDFData(val, buffers);
        }),
    );
    return result;
}
