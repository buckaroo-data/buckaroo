/**
 * End-to-end integration: xorq parquet bytes  →  hyparquet decode  →
 * DFViewerInfinite (Raw mode)  →  AG-Grid rowData.
 *
 * Mirrors the existing DFViewerInfinite.test.tsx pattern: AgGridReact is
 * mocked and we inspect ``latestAgGridProps.gridOptions.rowData`` —
 * that's the surface where "what will be rendered into the grid DOM"
 * is captured. AG-Grid's actual cell DOM is produced via virtual
 * scrolling + canvas, neither of which renders cleanly in jsdom; this
 * mock-and-inspect approach is what the rest of the JS test suite uses.
 *
 * Asserts that every cell value the Python widget intended to put into
 * the DOM survives the full pipeline.
 */
import { render } from "@testing-library/react";
import { parquetRead, parquetMetadata } from "hyparquet";

import { DFViewerInfinite } from "./DFViewerInfinite";
import { DFData, DFViewerConfig } from "./DFWhole";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const fixture = require("./test-fixtures/xorq_window_parquet.json");

let latestAgGridProps: any = null;

jest.mock("ag-grid-react", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const React = require("react");
    return {
        AgGridReact: React.forwardRef((props: any, ref: any) => {
            latestAgGridProps = props;
            React.useImperativeHandle(ref, () => ({
                api: { setGridOption: jest.fn() },
            }));
            React.useEffect(() => {
                props.onGridReady?.({
                    api: { setGridOption: jest.fn() },
                });
            }, [props]);
            return <div data-testid="ag-grid-react-mock" />;
        }),
    };
});

jest.mock("../useColorScheme", () => ({
    useColorScheme: () => "light",
}));

function b64ToArrayBuffer(b64: string): ArrayBuffer {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
}

/**
 * Convert hyparquet's BigInt (from parquet INT64) to Number, matching
 * what resolveDFData's parseParquetRow does. Without this the widget's
 * ``JSON.stringify(data_wrapper.data)`` (used as a memo signature)
 * blows up — TypeError: Do not know how to serialize a BigInt.
 */
function sanitizeRow(row: Record<string, any>): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(row)) {
        out[k] = typeof v === "bigint" ? Number(v) : v;
    }
    return out;
}

async function decodeFixture(): Promise<DFData> {
    const buf = b64ToArrayBuffer(fixture.data);
    const metadata = parquetMetadata(buf);
    const rows: any[] = [];
    await parquetRead({
        file: buf,
        metadata,
        rowFormat: "object",
        onComplete: (data: any[]) => { rows.push(...data); },
    });
    return rows.map(sanitizeRow) as DFData;
}

// Match the column_config that XorqBuckarooInfiniteWidget would emit.
const xorqViewerConfig: DFViewerConfig = {
    pinned_rows: [],
    left_col_configs: [],
    column_config: [
        { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
        {
            col_name: "a",
            header_name: "price",
            displayer_args: {
                displayer: "float",
                min_fraction_digits: 2,
                max_fraction_digits: 2,
            },
        },
        { col_name: "b", header_name: "name", displayer_args: { displayer: "string" } },
    ],
    component_config: {},
};

describe("xorq parquet → DFViewerInfinite → grid rowData", () => {
    beforeEach(() => {
        latestAgGridProps = null;
    });

    it("decoded xorq rows reach AgGridReact as rowData", async () => {
        const rows = await decodeFixture();
        expect(rows).toHaveLength(fixture.row_count);

        render(
            <DFViewerInfinite
                data_wrapper={{ data_type: "Raw", data: rows, length: rows.length }}
                df_viewer_config={xorqViewerConfig}
                summary_stats_data={[]}
                setActiveCol={jest.fn()}
            />,
        );

        // AG-Grid would render these as cells; the mock captures them on
        // the way in. This is the same surface DFViewerInfinite.test.tsx
        // asserts on.
        expect(latestAgGridProps).not.toBeNull();
        expect(latestAgGridProps.gridOptions.rowModelType).toBe("clientSide");
        const rowData: Record<string, unknown>[] = latestAgGridProps.gridOptions.rowData;
        expect(rowData).toHaveLength(fixture.row_count);

        // Index column carries absolute window offsets [start, end).
        const expectedIndices: number[] = [];
        for (let i = fixture.start; i < fixture.end; i++) expectedIndices.push(i);
        expect(rowData.map(r => Number(r.index))).toEqual(expectedIndices);

        // Names land in column 'b' as native UTF8 strings (no JSON quotes).
        const names = rowData.map(r => r.b);
        expect(names).toEqual(fixture.expected_names_at_offset);
        for (const n of names) {
            expect(typeof n).toBe("string");
            expect((n as string).startsWith('"')).toBe(false);
        }

        // Prices land in column 'a' as numbers.
        for (const r of rowData) {
            expect(typeof r.a).toBe("number");
        }
    });

    it("column_def fields wire up to the parquet column names", async () => {
        const rows = await decodeFixture();
        render(
            <DFViewerInfinite
                data_wrapper={{ data_type: "Raw", data: rows, length: rows.length }}
                df_viewer_config={xorqViewerConfig}
                summary_stats_data={[]}
                setActiveCol={jest.fn()}
            />,
        );

        // Each column_def needs a `field` matching a key in rowData,
        // otherwise AG-Grid renders blank cells. Spot-check the columns
        // we control come through correctly.
        const colDefs: any[] = latestAgGridProps.gridOptions.columnDefs;
        const fields = colDefs.map(c => c.field);
        for (const expected of fixture.rewritten_columns) {
            expect(fields).toContain(expected);
        }

        // And every field actually has data in the rows.
        for (const f of fixture.rewritten_columns) {
            for (const row of rows) {
                expect(row).toHaveProperty(f);
            }
        }
    });
});
