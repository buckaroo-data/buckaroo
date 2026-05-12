/**
 * Integration test: BuckarooInfiniteWidget under an autocleaning toggle.
 *
 * Reproduces the user's report from Full-tour.ipynb: "Just toggling the
 * cleaning method twice triggered React error #300" (Rendered fewer hooks
 * than expected).
 *
 * Production flow this test mirrors:
 *   1. Widget mounts with summary stats containing histogram + chart values.
 *   2. User flips cleaning_method in the status bar.
 *   3. Python regenerates summary stats; new `df_data_dict.summary_stats`
 *      comes back with values for some columns potentially missing or
 *      shape-changed.
 *   4. AG-Grid keeps the same cell-fiber instances and just sets new
 *      pinnedTopRowData via setGridOption — pushing fresh `value` props
 *      into the same React fibers used for the pinned cells.
 *   5. If any cellRenderer's hook count varies by value-shape branch,
 *      React throws #300 / #310 depending on direction.
 *
 * Unlike the existing flash matrix tests (which stub AG-Grid to a `<div/>`
 * and never actually mount cell renderers), this test installs an AG-Grid
 * mock that walks `pinnedTopRowData × columnDefs` and renders each cell
 * through `cellRendererSelector` — the same selector path that ships to
 * production. That's the only way the bug surfaces in jsdom: AG-Grid's
 * cell layer is where the hook violation actually fires.
 */

// jsdom polyfill for crypto.randomUUID (used by HistogramCell.gensym).
{
    let n = 0;
    const existing: any = (globalThis as any).crypto || {};
    if (typeof existing.randomUUID !== "function") {
        try {
            Object.defineProperty(existing, "randomUUID", {
                configurable: true,
                value: () => `test-uuid-${++n}`,
            });
        } catch {
            Object.defineProperty(globalThis, "crypto", {
                configurable: true,
                value: { ...existing, randomUUID: () => `test-uuid-${++n}` },
            });
        }
    }
}

// ts-jest doesn't apply esModuleInterop. Patch the React default import so
// HistogramCell.tsx and ChartCell.tsx (which both do `import React from "react"`)
// see a working React object at runtime.
jest.mock("react", () => {
    const actual = jest.requireActual("react");
    return { __esModule: true, default: actual, ...actual };
});

import { render } from "@testing-library/react";
import type {
    ColDef,
    GridApi,
    ICellRendererParams,
    CellRendererSelectorResult,
} from "ag-grid-community";

import { BuckarooInfiniteWidget } from "../BuckarooWidgetInfinite";
import { KeyAwareSmartRowCache } from "./SmartRowCache";
import type { BuckarooOptions, BuckarooState, DFMeta } from "../WidgetTypes";
import type { DFData, DFViewerConfig } from "./DFWhole";
import type { IDisplayArgs } from "./gridUtils";

// recharts pulls in DOM measurement; stub the surface both cell renderers touch.
jest.mock("recharts", () => {
    const React = require("react") as typeof import("react");
    const stub = ({ children }: any) =>
        React.createElement("div", { "data-testid": "recharts-mock" }, children);
    return {
        Area: () => null,
        Bar: () => null,
        BarChart: stub,
        ComposedChart: stub,
        Line: () => null,
        Tooltip: () => null,
    };
});

// Stub StatusBar so its own AG-Grid usage doesn't get picked up by our mock.
jest.mock("../StatusBar", () => ({
    StatusBar: () => null,
}));

// Custom AG-Grid mock that ACTUALLY renders each pinned-row cell via the
// cellRendererSelector path. DFViewerInfinite sets pinnedTopRowData via
// the imperative api.setGridOption call (not via gridOptions props), so
// the mock keeps its own React state for pinnedTopRowData and updates it
// when setGridOption is invoked.
jest.mock("ag-grid-react", () => {
    const React = require("react") as typeof import("react");

    const renderOneCell = (
        rowData: any,
        col: ColDef,
        cellRendererSelector: any,
        rowPinned: "top" | "bottom" | undefined,
        outerContext: any,
    ): any => {
        const value = col.field ? rowData[col.field] : undefined;
        const params: Partial<ICellRendererParams> = {
            value,
            data: rowData,
            colDef: col,
            column: { getColId: () => col.field ?? "" } as any,
            api: {} as GridApi,
            context: outerContext,
            node: { rowPinned, data: rowData } as any,
        };
        let component: any = col.cellRenderer;
        if (!component && typeof cellRendererSelector === "function") {
            const sel: CellRendererSelectorResult | undefined = cellRendererSelector(
                params as ICellRendererParams,
            );
            component = sel?.component ?? null;
        }
        if (!component) return null;
        if (typeof component === "string") return null; // skip 'agCheckboxCellRenderer' etc.
        return React.createElement(component, { ...params, key: col.field });
    };

    return {
        AgGridReact: React.forwardRef((props: any, ref: any) => {
            const [pinnedTopRowData, setPinnedTopRowData] = React.useState<any[]>([]);
            const [rowData, setRowData] = React.useState<any[]>([]);

            const api = React.useMemo(
                () => ({
                    setGridOption: (key: string, value: any) => {
                        if (key === "pinnedTopRowData") setPinnedTopRowData(value || []);
                        if (key === "rowData") setRowData(value || []);
                    },
                }),
                [],
            );

            React.useImperativeHandle(ref, () => ({ api }), [api]);

            // Fire onGridReady so DFViewerInfinite's imperative-API path runs,
            // pushing the initial pinnedTopRowData into our captured state.
            React.useEffect(() => {
                props.onGridReady?.({ api });
            }, [api]);

            const columnDefs: ColDef[] = props.columnDefs ?? [];
            const cellRendererSelector = props.defaultColDef?.cellRendererSelector;

            const renderRow = (rd: any, idx: number, pinned: "top" | undefined) =>
                React.createElement(
                    "div",
                    { key: `row-${pinned ?? "body"}-${idx}`, "data-testid": `row-${idx}` },
                    columnDefs.map((c) =>
                        renderOneCell(rd, c, cellRendererSelector, pinned, props.context),
                    ),
                );

            return React.createElement(
                "div",
                { "data-testid": "ag-grid-render-mock" },
                pinnedTopRowData.map((rd, i) => renderRow(rd, i, "top")),
                rowData.map((rd, i) => renderRow(rd, i, undefined)),
            );
        }),
    };
});

// ---------- realistic data --------------------------------------------------

const validHistogram = [
    { name: "true", true: 60, population: 60 },
    { name: "false", false: 40, population: 40 },
];
const altHistogram = [
    { name: "longtail", longtail: 100, population: 100 },
];
const validChart = [
    { lineRed: 1, lineBlue: 2 },
    { lineRed: 3, lineBlue: 4 },
];
const altChart = [
    { lineRed: 5 },
];

const dfViewerConfig: DFViewerConfig = {
    pinned_rows: [
        { primary_key_val: "histogram", displayer_args: { displayer: "histogram" } },
        { primary_key_val: "chart", displayer_args: { displayer: "chart" } },
    ],
    column_config: [
        { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
        { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
        { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
    ],
    left_col_configs: [],
};

const baseDisplayArgs: Record<string, IDisplayArgs> = {
    main: {
        data_key: "main",
        df_viewer_config: dfViewerConfig,
        summary_stats_key: "summary_stats",
    },
};

const baseDfMeta: DFMeta = {
    total_rows: 50,
    columns: 3,
    filtered_rows: 50,
    rows_shown: 50,
};

const baseOptions: BuckarooOptions = {
    sampled: [],
    cleaning_method: ["", "aggressive", "conservative"],
    post_processing: [],
    df_display: ["main"],
    show_commands: [],
};

const initialState: BuckarooState = {
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
};

// Summary stats data — each row's `index` matches one of the pinned_rows.
// `a` is a numeric column with both kinds of stats; `b` loses its chart data
// after the first toggle to simulate a column whose autoclean strategy
// dropped the time-series view.
const summaryStatsBefore: DFData = [
    { index: "histogram", a: validHistogram, b: validHistogram },
    { index: "chart", a: validChart, b: validChart },
];

const summaryStatsAfterToggle1: DFData = [
    // `b` loses BOTH its histogram and chart data after aggressive cleaning
    // (column dtype change → no per-row stats). The cells receive the
    // string sentinel that pinned-row cells fall back to when the column
    // has no value — flipping HistogramCell and ChartCell on column `b`
    // into their early-return branches.
    { index: "histogram", a: altHistogram, b: "histogram" },
    { index: "chart", a: altChart, b: "chart" },
];

const summaryStatsAfterToggle2: DFData = [
    { index: "histogram", a: validHistogram, b: validHistogram },
    { index: "chart", a: validChart, b: validChart },
];

const widget = (
    cleaning_method: BuckarooState["cleaning_method"],
    summaryStats: DFData,
    src: KeyAwareSmartRowCache,
) => (
    <BuckarooInfiniteWidget
        df_data_dict={{ summary_stats: summaryStats }}
        df_display_args={baseDisplayArgs}
        df_meta={baseDfMeta}
        operations={[]}
        on_operations={jest.fn()}
        operation_results={{} as any}
        command_config={{ argspecs: {}, defaultArgs: {} }}
        buckaroo_state={{ ...initialState, cleaning_method }}
        on_buckaroo_state={jest.fn()}
        buckaroo_options={baseOptions}
        src={src}
    />
);

describe("BuckarooInfiniteWidget — autocleaning toggle", () => {
    it("does not throw a React hook error when cleaning_method is toggled twice", () => {
        const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
        try {
            const src = new KeyAwareSmartRowCache(() => {});

            // Mount with the "before autoclean" state — valid histogram +
            // chart values in every pinned cell.
            const { rerender, container } = render(widget(false, summaryStatsBefore, src));

            // Sanity: the mock must have rendered cells. 2 pinned rows ×
            // 2 numeric columns = 4 chart/histogram mounts. If this is 0,
            // the cell-renderers never fired and the test is vacuous.
            const rechartsNodes = container.querySelectorAll(
                '[data-testid="recharts-mock"]',
            );
            expect(rechartsNodes.length).toBeGreaterThan(0);

            // First toggle: cleaning_method = "aggressive". Summary stats
            // regenerate. Column `b` loses its chart data (now the string
            // sentinel) — the chart cell-fiber for column `b` rerenders
            // with a different value shape.
            expect(() => {
                rerender(widget("aggressive", summaryStatsAfterToggle1, src));
            }).not.toThrow();

            // Second toggle: cleaning_method = "conservative". Data comes
            // back for column `b`. Same cell-fibers, value shape flips.
            expect(() => {
                rerender(widget("conservative", summaryStatsAfterToggle2, src));
            }).not.toThrow();

            // Belt-and-braces: no React errors were logged either.
            const reactErrors = errSpy.mock.calls.filter((args) =>
                args.some(
                    (a) =>
                        typeof a === "string" &&
                        /Rendered (more|fewer) hooks|Minified React error #(300|310)/i.test(
                            a,
                        ),
                ),
            );
            expect(reactErrors).toEqual([]);
        } finally {
            errSpy.mockRestore();
        }
    });
});
