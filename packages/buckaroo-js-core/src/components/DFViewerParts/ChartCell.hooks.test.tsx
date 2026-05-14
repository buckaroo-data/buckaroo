/**
 * Pins down a Rules-of-Hooks violation in ChartCell.
 *
 * getChartCell() returns a ChartCell that early-returns <span/> when
 * props.value is undefined or not an array (0 hooks). In the "valid array"
 * branch it returns `TypedChartCellInner({...})` — a plain function call,
 * not JSX. React therefore counts the `React.useState(...)` inside
 * TypedChartCellInner on ChartCell's own hook list.
 *
 * Hook count is 0 in the invalid branch and 1 in the valid branch. AG-Grid
 * reuses cell fiber instances across rerenders; when summary stats
 * regenerate (e.g. user toggles cleaning_method on the autocleaning system)
 * the same instance flips between branches and React throws minified error
 * #300 / #310. Same shape as the HistogramCell bug fixed in ba4e2394.
 */
// ts-jest in this repo doesn't apply esModuleInterop, so the default import
// `import React from "react"` in ChartCell.tsx resolves to `undefined` at
// runtime under jsdom. Provide a `.default` so React.useState is callable
// and React can actually detect the hook-count mismatch this test pins down.
jest.mock("react", () => {
    const actual = jest.requireActual("react");
    return { __esModule: true, default: actual, ...actual };
});

import { render } from "@testing-library/react";
import { getChartCell, LineObservation } from "./ChartCell";

// recharts pulls in DOM-measurement code that doesn't run cleanly under
// jsdom — stub the few exports ChartCell touches.
jest.mock("recharts", () => {
    const React = require("react");
    return {
        Area: () => null,
        Bar: () => null,
        Line: () => null,
        Tooltip: () => null,
        ComposedChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "composedchart-mock" }, children),
    };
});

const ChartCell = getChartCell({ displayer: "chart" });

const validChart: LineObservation[] = [
    { barRed: 10, lineBlue: 20 },
    { barRed: 30, lineBlue: 40 },
];

const mkProps = (value: any) => ({
    value,
    api: {} as any,
    colDef: { cellClass: "" } as any,
    column: {} as any,
    context: {},
});

// Helper: collect console.error calls that match a React hook violation,
// independent of whether the violation also throws synchronously. React 18
// surfaces some hook mismatches as throws and others as dev-mode warnings.
const collectHookErrors = (errSpy: jest.SpyInstance) =>
    errSpy.mock.calls.filter((args: unknown[]) =>
        args.some(
            (a: unknown) =>
                typeof a === "string" &&
                /Rendered (more|fewer) hooks|Minified React error #(300|310)|Invalid hook call|change the order of Hooks/i.test(
                    a,
                ),
        ),
    );

describe("ChartCell — Rules of Hooks", () => {
    it("does not violate hook rules when value flips from invalid to a valid chart array", () => {
        const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
        try {
            // First render: value is the literal string "chart" (the sentinel
            // pinned-row value for index/non-data columns). ChartCell returns
            // <span/>. Zero hooks recorded on the fiber.
            const { rerender } = render(<ChartCell {...mkProps("chart")} />);

            // Same component instance re-renders with a valid array. The valid
            // branch calls React.useState via TypedChartCellInner, bumping the
            // hook count from 0 -> 1 on the same fiber.
            expect(() => {
                rerender(<ChartCell {...mkProps(validChart)} />);
            }).not.toThrow();
            expect(collectHookErrors(errSpy)).toEqual([]);
        } finally {
            errSpy.mockRestore();
        }
    });

    it("does not violate hook rules when value flips from a valid chart array to invalid", () => {
        const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
        try {
            const { rerender } = render(<ChartCell {...mkProps(validChart)} />);
            expect(() => {
                rerender(<ChartCell {...mkProps(undefined)} />);
            }).not.toThrow();
            expect(collectHookErrors(errSpy)).toEqual([]);
        } finally {
            errSpy.mockRestore();
        }
    });
});
