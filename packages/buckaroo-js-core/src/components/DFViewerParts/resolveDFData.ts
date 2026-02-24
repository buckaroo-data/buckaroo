import { tableFromIPC } from '@uwdata/flechette';
import { DFData, DFDataRow, DFDataOrPayload, ParquetB64Payload, IpcB64Payload } from './DFWhole';

function isParquetB64(val: unknown): val is ParquetB64Payload {
    return (
        val !== null &&
        typeof val === 'object' &&
        !Array.isArray(val) &&
        (val as any).format === 'parquet_b64' &&
        typeof (val as any).data === 'string'
    );
}

function isIpcB64(val: unknown): val is IpcB64Payload {
    return (
        val !== null &&
        typeof val === 'object' &&
        !Array.isArray(val) &&
        (val as any).format === 'ipc_b64' &&
        typeof (val as any).data === 'string'
    );
}

const _cache = new Map<string, DFData>();
const MAX_CACHE = 8;

function cacheSet(key: string, value: DFData) {
    if (_cache.size >= MAX_CACHE) {
        const first = _cache.keys().next().value;
        if (first !== undefined) _cache.delete(first);
    }
    _cache.set(key, value);
}

function b64ToArrayBuffer(b64: string): ArrayBuffer {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
        bytes[i] = bin.charCodeAt(i);
    }
    return bytes.buffer;
}

function parseRowJsonCells(row: Record<string, any>): DFDataRow {
    const parsed: DFDataRow = {};
    for (const [key, val] of Object.entries(row)) {
        if (key === 'index' || key === 'level_0') {
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

function decodeB64Payload(b64Data: string): DFData {
    const buf = b64ToArrayBuffer(b64Data);
    const table = tableFromIPC(buf, { useProxy: false });
    const rows = table.toArray() as DFDataRow[];
    return rows.map(parseRowJsonCells);
}

export function resolveDFData(val: DFDataOrPayload | undefined | null): DFData {
    if (val === undefined || val === null) return [];
    if (Array.isArray(val)) return val as DFData;

    if (isIpcB64(val) || isParquetB64(val)) {
        const cached = _cache.get(val.data);
        if (cached && cached.length > 0) return cached;

        try {
            const result = decodeB64Payload(val.data);
            cacheSet(val.data, result);
            return result;
        } catch (e) {
            console.error('resolveDFData: failed to decode b64 payload', e);
            return [];
        }
    }

    console.warn('resolveDFData: unknown payload format', val);
    return [];
}

export async function resolveDFDataAsync(val: DFDataOrPayload | undefined | null): Promise<DFData> {
    return resolveDFData(val);
}

export async function preResolveDFDataDict(
    dict: Record<string, DFDataOrPayload> | undefined | null
): Promise<Record<string, DFDataOrPayload>> {
    if (!dict) return {};
    const result: Record<string, DFDataOrPayload> = {};
    for (const [key, val] of Object.entries(dict)) {
        if (isIpcB64(val) || isParquetB64(val)) {
            result[key] = resolveDFData(val);
        } else {
            result[key] = val;
        }
    }
    return result;
}
