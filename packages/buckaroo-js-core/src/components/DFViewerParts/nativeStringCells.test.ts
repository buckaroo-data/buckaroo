/**
 * Regression test for the native-parquet string-cell corruption.
 *
 * The polars / xorq / lazy infinite paths write *native* parquet UTF8
 * strings (df.write_parquet / pq.write_table), unlike the pandas path which
 * JSON-encodes object cells via fastparquet. decodeDFData runs every
 * parquet_buffer frame through parseParquetRow, which JSON-parses every
 * string cell — correct for the pandas convention, wrong for native bytes:
 * a string whose text is valid JSON ("null", "123", '{"a": 1}') is silently
 * coerced to null / 123 / an object.
 *
 * The fixture holds the exact bytes both backends emit for a frame of such
 * strings, plus the pyarrow ground-truth decode (the strings, unchanged).
 */
import { decodeDFData } from './resolveDFData';
import { DFData, DFEnvelope } from './DFWhole';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const fixture = require('./test-fixtures/native_string_cells_parquet.json');

function b64ToDataView(b64: string): DataView {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new DataView(bytes.buffer);
}

describe('native-parquet string cells survive decodeDFData unchanged', () => {
    for (const backend of ['polars', 'xorq'] as const) {
        const blob = fixture.backends[backend];

        it(`${backend}: every string cell stays a string (no JSON.parse coercion)`, async () => {
            const env = blob.envelope as DFEnvelope;
            const rows = await decodeDFData(env, [b64ToDataView(blob.data)]);
            expect(rows).toEqual(blob.expected as DFData);
        });

        it(`${backend}: JSON-looking strings are not coerced to null/number/object`, async () => {
            const env = blob.envelope as DFEnvelope;
            const rows = await decodeDFData(env, [b64ToDataView(blob.data)]);
            const row0 = rows[0];
            expect(row0.b).toBe('null');
            expect(row0.c).toBe('true');
            expect(row0.d).toBe('123');
            expect(row0.e).toBe('{"a": 1}');
            expect(row0.f).toBe('[1, 2]');
            for (const col of ['b', 'c', 'd', 'e', 'f']) {
                expect(typeof row0[col]).toBe('string');
            }
        });
    }
});

// End-to-end exercise of the three json_columns branches against the real
// polars bytes — the same frame decoded under each envelope variant. The
// committed envelope carries json_columns: []; here we override it to pin the
// decoder's behavior across the whole spectrum (parse-all → subset → none).
describe('decodeDFData json_columns branches on native string bytes', () => {
    const blob = fixture.backends.polars;
    const bytes = () => [b64ToDataView(blob.data)];

    it('absent json_columns → legacy parse-all coerces JSON-looking strings (the #937 bug)', async () => {
        // No json_columns key ⇒ undefined ⇒ every string cell is JSON-parsed.
        // This is exactly the corruption the fix prevents for native frames.
        const env: DFEnvelope = { format: 'parquet_buffer', buffer_index: 0 };
        const row0 = (await decodeDFData(env, bytes()))[0];
        expect(row0.b).toBeNull();
        expect(row0.c).toBe(true);
        expect(row0.d).toBe(123);
        expect(row0.e).toEqual({ a: 1 });
        expect(row0.f).toEqual([1, 2]);
    });

    it('named subset → only listed columns are parsed, the rest stay strings', async () => {
        // Declare just 'b' and 'd' as JSON-encoded: those coerce, the siblings
        // (rewritten-name space) pass through untouched.
        const env: DFEnvelope = { format: 'parquet_buffer', buffer_index: 0, json_columns: ['b', 'd'] };
        const row0 = (await decodeDFData(env, bytes()))[0];
        expect(row0.b).toBeNull();
        expect(row0.d).toBe(123);
        expect(row0.c).toBe('true');
        expect(row0.e).toBe('{"a": 1}');
        expect(row0.f).toBe('[1, 2]');
    });

    it('empty json_columns → nothing is parsed (the native-sender contract)', async () => {
        const env: DFEnvelope = { format: 'parquet_buffer', buffer_index: 0, json_columns: [] };
        const row0 = (await decodeDFData(env, bytes()))[0];
        for (const col of ['b', 'c', 'd', 'e', 'f']) {
            expect(typeof row0[col]).toBe('string');
        }
    });
});
