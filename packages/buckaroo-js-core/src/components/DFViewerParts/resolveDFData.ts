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
            parsed[key] = val;
        } else if (typeof val === 'string') {
            try {
                parsed[key] = JSON.parse(val);
            } catch {
                parsed[key] = val;
            }
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
 * hyparquet's parquetRead with onComplete fires synchronously when given an
 * in-memory ArrayBuffer, so this function is synchronous.
 */
export function resolveDFData(val: DFDataOrPayload | undefined | null): DFData {
    if (val === undefined || val === null) return [];
    if (Array.isArray(val)) return val as DFData;

    if (isParquetB64(val)) {
        // Check cache
        const cached = _cache.get(val.data);
        if (cached) return cached;

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
                },
            });
            cacheSet(val.data, result);
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
