// recharts pulls in DOM-measurement code that doesn't run cleanly under
// jsdom — stub the exports ChartCell touches (same approach as
// HistogramCell.hooks.test.tsx).
jest.mock("recharts", () => ({
    Area: () => null,
    ComposedChart: () => null,
    Line: () => null,
    Tooltip: () => null,
    Bar: () => null,
}));

import { formatTooltipValue } from "./ChartCell";

describe("formatTooltipValue", () => {
    it("rounds finite numbers to 1dp", () => {
        expect(formatTooltipValue(10.00083260202892)).toBe("10.0");
        expect(formatTooltipValue(0)).toBe("0.0");
    });

    it("does not crash on non-numeric payload values", () => {
        expect(formatTooltipValue("longtail")).toBe("longtail");
        expect(formatTooltipValue(undefined)).toBe("");
        expect(formatTooltipValue(null)).toBe("");
    });
});
