import { render } from "@testing-library/react";
import { ColDef, ValueFormatterParams } from "ag-grid-community";

import { getHighlightTextCellRenderer } from "./OtherRenderers";
import { getStringFormatter } from "./Displayer";
import { dfToAgrid } from "./gridUtils";
import { DFViewerConfig } from "./DFWhole";

const plainFmt = getStringFormatter({ displayer: "string" });
const mkProps = (value: unknown) => ({ value } as ValueFormatterParams);

describe("string displayer highlight", () => {
    it("highlights phrase matches", () => {
        const R = getHighlightTextCellRenderer(plainFmt, { phrase: "error" });
        const { container } = render(<R {...mkProps("ERROR: load error")} />);
        const marks = Array.from(container.querySelectorAll("mark")).map(
            (m) => m.textContent,
        );
        expect(marks).toEqual(["ERROR", "error"]);
    });

    it("highlights regex matches", () => {
        const R = getHighlightTextCellRenderer(plainFmt, { regex: "\\d+" });
        const { container } = render(<R {...mkProps("err 42 / err 7")} />);
        const marks = Array.from(container.querySelectorAll("mark")).map(
            (m) => m.textContent,
        );
        expect(marks).toEqual(["42", "7"]);
    });

    it("dfToAgrid wires cellRenderer (not just valueFormatter) when highlight_regex is set", () => {
        // This is the integration point that the Python-side delivery feeds.
        // If dfToAgrid only set valueFormatter, the highlight renderer would
        // never be invoked by AG-Grid — the cell would render the raw value.
        const cfg: DFViewerConfig = {
            pinned_rows: [],
            left_col_configs: [],
            column_config: [{
                col_name: "comments",
                header_name: "comments",
                displayer_args: { displayer: "string", max_length: 2000, highlight_regex: "area" },
            }],
        };
        const cols = dfToAgrid(cfg) as ColDef[];
        expect(cols).toHaveLength(1);
        expect(cols[0].cellRenderer).toBeDefined();
        expect(cols[0].valueFormatter).toBeUndefined();

        // And the resulting renderer wraps matches in <mark> when given a real value.
        const Renderer = cols[0].cellRenderer as any;
        const { container } = render(<Renderer {...mkProps("Hood filter area with grease build up")} />);
        const marks = Array.from(container.querySelectorAll("mark")).map((m) => m.textContent);
        expect(marks).toEqual(["area"]);
    });

    it("dfToAgrid wires cellRenderer when highlight_phrase is set", () => {
        const cfg: DFViewerConfig = {
            pinned_rows: [],
            left_col_configs: [],
            column_config: [{
                col_name: "comments",
                header_name: "comments",
                displayer_args: { displayer: "string", max_length: 2000, highlight_phrase: ["area"], highlight_color: "red" },
            }],
        };
        const cols = dfToAgrid(cfg) as ColDef[];
        expect(cols[0].cellRenderer).toBeDefined();
        expect(cols[0].valueFormatter).toBeUndefined();
        const Renderer = cols[0].cellRenderer as any;
        const { container } = render(<Renderer {...mkProps("Hood filter area with grease")} />);
        const mark = container.querySelector("mark") as HTMLElement;
        expect(mark?.textContent).toBe("area");
        expect(mark?.style.backgroundColor).toBe("red");
    });
});

// These tests document a memoization blind spot in DFViewerInfinite's
// gridOptions useMemo dep list, which historically uses
// `JSON.stringify(styledColumns)`. Adding `highlight_regex` to displayer_args
// flips a column from {valueFormatter: fn} to {cellRenderer: fn} — but
// JSON.stringify silently drops function values, so the two stringifications
// are equal and useMemo never recomputes. AG-Grid never sees the new colDefs
// and existing cells keep their old rendering. The fix is to gate on the
// SOURCE (df_viewer_config.column_config), which is plain data.
describe("dfToAgrid memoization signature: function-prop blind spot", () => {
    const mkCfg = (extras: Record<string, unknown> = {}): DFViewerConfig => ({
        pinned_rows: [],
        left_col_configs: [],
        column_config: [{
            col_name: "c",
            header_name: "c",
            displayer_args: { displayer: "string", max_length: 35, ...extras },
        }],
    });

    it("JSON.stringify on post-dfToAgrid columns can't see the renderer flip", () => {
        const plain = dfToAgrid(mkCfg()) as ColDef[];
        const withHl = dfToAgrid(mkCfg({ highlight_regex: "x" })) as ColDef[];

        // The colDefs ARE functionally different — one has cellRenderer, the
        // other only valueFormatter:
        expect(plain[0].cellRenderer).toBeUndefined();
        expect(plain[0].valueFormatter).toBeDefined();
        expect(withHl[0].cellRenderer).toBeDefined();
        expect(withHl[0].valueFormatter).toBeUndefined();

        // …but JSON.stringify drops the function values, so the signatures
        // collide. A useMemo gated on this string would not recompute.
        expect(JSON.stringify(plain)).toBe(JSON.stringify(withHl));
    });

    it("JSON.stringify on the source column_config DOES capture the flip", () => {
        const plain = mkCfg().column_config;
        const withHl = mkCfg({ highlight_regex: "x" }).column_config;
        expect(JSON.stringify(plain)).not.toBe(JSON.stringify(withHl));
    });

    it("reference equality on column_config (or styledColumns) is sufficient when Python re-pushes the tree", () => {
        // anywidget deserializes a fresh JSON tree on every Python push, so
        // df_viewer_config.column_config is a *new* array ref each update —
        // a cheap reference dep catches every meaningful change.
        const cfg1 = mkCfg();
        const cfg2 = mkCfg({ highlight_regex: "x" });
        expect(cfg1.column_config).not.toBe(cfg2.column_config);
    });
});
