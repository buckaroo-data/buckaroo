/**
 * Sparkline rendering contract for the chart cell (pinned rows and data
 * columns):
 *  - every line series draws at 1px with per-point dots disabled — the
 *    100x24 chart gets CSS-scaled to fill its grid cell, which turns the
 *    recharts defaults (dots + scaled stroke) into a fat blobby squiggle
 *  - a hidden YAxis pads the plot by 2px top and bottom so a series whose
 *    values sit exactly at dataMin/dataMax (e.g. the "after" side of a
 *    diff whose values collapsed) isn't drawn on the plot border where
 *    the clip rect swallows half the stroke
 */
jest.mock("react", () => {
    const actual = jest.requireActual("react");
    return { __esModule: true, default: actual, ...actual };
});

import { render } from "@testing-library/react";
import { getChartCell, LineObservation } from "./ChartCell";

// recharts pulls in DOM-measurement code that doesn't run cleanly under
// jsdom — stub the exports ChartCell touches, keeping Line/YAxis props
// inspectable in the rendered tree.
jest.mock("recharts", () => {
    const React = require("react");
    return {
        Area: () => null,
        Bar: () => null,
        Line: ({ dataKey, dot, strokeWidth }: any) =>
            React.createElement("div", {
                "data-testid": `line-${dataKey}`,
                "data-dot": String(dot),
                "data-stroke-width": String(strokeWidth),
            }),
        Tooltip: () => null,
        YAxis: ({ hide, padding }: any) =>
            React.createElement("div", {
                "data-testid": "yaxis-mock",
                "data-hide": String(hide),
                "data-padding-top": String(padding?.top),
                "data-padding-bottom": String(padding?.bottom),
            }),
        ComposedChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "composedchart-mock" }, children),
    };
});

const ChartCell = getChartCell({ displayer: "chart" });

const validChart: LineObservation[] = [{ lineRed: 10 }, { lineRed: 20 }];

const mkProps = (value: any) => ({
    value,
    api: {} as any,
    colDef: { cellClass: "" } as any,
    column: {} as any,
    context: {},
});

describe("ChartCell sparkline rendering", () => {
    it("draws every line series at 1px with dots disabled", () => {
        const { container } = render(<ChartCell {...mkProps(validChart)} />);
        const lines = container.querySelectorAll('[data-testid^="line-"]');
        expect(lines.length).toBeGreaterThan(0);
        lines.forEach((line) => {
            expect(line.getAttribute("data-dot")).toBe("false");
            expect(line.getAttribute("data-stroke-width")).toBe("1");
        });
    });

    it("pads the y domain via a hidden axis so edge-hugging series are not clipped", () => {
        const { getByTestId } = render(<ChartCell {...mkProps(validChart)} />);
        const axis = getByTestId("yaxis-mock");
        expect(axis.getAttribute("data-hide")).toBe("true");
        expect(axis.getAttribute("data-padding-top")).toBe("2");
        expect(axis.getAttribute("data-padding-bottom")).toBe("2");
    });
});
