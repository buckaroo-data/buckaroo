/**
 * Per-bar color support on the histogram cell: a HistogramBar may carry
 * `color`, and the population Bar renders one recharts Cell per datum so
 * the color lands on that individual bar. Diff views use this to paint the
 * change-distribution histogram with the same color key as the data cells;
 * bars without a color keep the scheme default.
 */
// jsdom's `crypto` lacks `randomUUID`; HistogramCell's gensym() uses it.
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

// ts-jest in this repo doesn't apply esModuleInterop, so the default import
// `import React from "react"` in HistogramCell.tsx resolves to `undefined`
// at runtime without a `.default` on the mock.
jest.mock("react", () => {
    const actual = jest.requireActual("react");
    return { __esModule: true, default: actual, ...actual };
});

import { render } from "@testing-library/react";
import type { ColDef, Column, Context, GridApi } from "ag-grid-community";
import { HistogramCell } from "./HistogramCell";

// recharts pulls in DOM-measurement code that doesn't run cleanly under
// jsdom — stub the exports HistogramCell touches, keeping Bar/Cell props
// inspectable in the rendered tree.
jest.mock("recharts", () => {
    const React = require("react");
    return {
        Bar: ({ children, dataKey }: any) =>
            React.createElement("div", { "data-testid": `bar-${dataKey}` }, children),
        BarChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "barchart-mock" }, children),
        Cell: ({ fill }: any) =>
            React.createElement("div", { "data-testid": "cell-mock", "data-fill": fill }),
        Tooltip: () => null,
    };
});

const mkProps = (value: any) => ({
    value,
    api: {} as GridApi,
    colDef: { cellClass: "" } as ColDef,
    column: {} as Column,
    context: {} as Context,
});

describe("HistogramCell per-bar colors", () => {
    it("renders one Cell per datum on the population bar, honoring bar.color", () => {
        const bars = [
            { name: "<-50%", population: 20, color: "#d62728" },
            { name: "~0%", population: 80 },
        ];
        const { getByTestId } = render(<HistogramCell {...mkProps(bars)} />);
        const popBar = getByTestId("bar-population");
        const cells = popBar.querySelectorAll('[data-testid="cell-mock"]');
        expect(cells).toHaveLength(2);
        expect(cells[0].getAttribute("data-fill")).toBe("#d62728");
        // Uncolored bars keep the scheme default fill — set, and not the
        // colored bar's value.
        expect(cells[1].getAttribute("data-fill")).toBeTruthy();
        expect(cells[1].getAttribute("data-fill")).not.toBe("#d62728");
    });
});
