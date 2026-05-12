/**
 * Pins down a Rules-of-Hooks violation in HistogramCell.
 *
 * HistogramCell calls useColorScheme() unconditionally (1 hook), then
 * early-returns <span/> when props.value is undefined or not an array.
 * In the "valid array" branch it returns `TypedHistogramCell({...})` —
 * a plain function call, not JSX. React therefore counts the
 * `React.useState(...)` inside TypedHistogramCell on HistogramCell's own
 * hook list.
 *
 * Hook count is 1 in the invalid branch and 2 in the valid branch. AG-Grid
 * reuses a single cell instance across rows/refreshes; when summary stats
 * regenerate (e.g. after the user toggles cleaning_method on the
 * autocleaning system), the same instance flips between branches and
 * React throws minified error #310: "Rendered more hooks than during
 * the previous render."
 */
// jsdom's `crypto` lacks `randomUUID`; HistogramCell's gensym() uses it.
// Without this polyfill the test crashes inside gensym BEFORE React reaches
// the `useState` call, masking the actual Rules-of-Hooks violation.
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
            // Fall back to redefining the whole crypto global.
            Object.defineProperty(globalThis, "crypto", {
                configurable: true,
                value: { ...existing, randomUUID: () => `test-uuid-${++n}` },
            });
        }
    }
}

// ts-jest in this repo doesn't apply esModuleInterop, so the default import
// `import React from "react"` in HistogramCell.tsx resolves to `undefined`
// at runtime. Provide a `.default` so React.useState is callable and React
// can actually detect the hook-count mismatch this test is pinning down.
jest.mock("react", () => {
    const actual = jest.requireActual("react");
    return { __esModule: true, default: actual, ...actual };
});

import { render } from "@testing-library/react";
import { HistogramCell } from "./HistogramCell";

// Do NOT mock useColorScheme to a plain () => "light" — that would erase
// the underlying React hook it calls (useSyncExternalStore) and remove the
// "first hook" from HistogramCell's invalid-branch render, hiding the
// hook-count mismatch we're trying to surface here.

// recharts pulls in DOM-measurement code that doesn't run cleanly under
// jsdom — stub the few exports HistogramCell touches.
jest.mock("recharts", () => {
    const React = require("react");
    return {
        Bar: () => null,
        BarChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "barchart-mock" }, children),
        Tooltip: () => null,
    };
});

const validHistogram = [
    { name: "true", true: 60, population: 60 },
    { name: "false", false: 40, population: 40 },
];

const mkProps = (value: any) => ({
    value,
    api: {} as any,
    colDef: { cellClass: "" } as any,
    column: {} as any,
    context: {},
});

describe("HistogramCell — Rules of Hooks", () => {
    it("does not change hook count when value flips from invalid to a valid histogram array", () => {
        const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
        try {
            // First render: value is the literal string "histogram" (what comes in
            // for the index column). HistogramCell calls useColorScheme then
            // returns <span/>. One hook recorded.
            const { rerender } = render(<HistogramCell {...mkProps("histogram")} />);

            // Same component instance re-renders with a valid array. The valid
            // branch additionally calls React.useState via TypedHistogramCell,
            // bumping the hook count from 1 -> 2 and tripping React error #310.
            expect(() => {
                rerender(<HistogramCell {...mkProps(validHistogram)} />);
            }).not.toThrow();
        } finally {
            errSpy.mockRestore();
        }
    });

    it("does not change hook count when value flips from a valid histogram array to invalid", () => {
        const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
        try {
            const { rerender } = render(<HistogramCell {...mkProps(validHistogram)} />);
            expect(() => {
                rerender(<HistogramCell {...mkProps(undefined)} />);
            }).not.toThrow();
        } finally {
            errSpy.mockRestore();
        }
    });
});
