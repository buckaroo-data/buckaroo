/**
 * Stories that exercise the BuckarooView autoHeight code path (#847).
 *
 * Rather than wire up a fake transport that returns parquet-encoded
 * infinite_resp messages (BuckarooView's getKeySmartRowCache decodes
 * parquet bytes off the wire), these stories drive DFViewerInfiniteDS
 * directly with an in-memory KeyAwareSmartRowCache — the same shortcut
 * SmallDFScroll.stories.tsx uses — but reproduce BuckarooView's two
 * autoHeight outputs verbatim:
 *
 *   1. component_config.layoutType = "autoHeight" stamped onto every
 *      df_display_args entry (gridUtils.getHeightStyle2 honors it).
 *   2. wrapper style: no `height: 100%` when autoHeight is true.
 *
 * Playwright then varies the storybook viewport (short / tall) and the
 * synthetic row count (small / large) to verify there are no spurious
 * gaps between:
 *
 *   - the last data row and the AG-Grid root wrapper bottom
 *   - the AG-Grid root wrapper and the BuckarooView-style wrapper bottom
 *   - the wrapper and the host container bottom
 *
 * Each story declares a fixed-pixel host (`data-testid="host"`) so the
 * test can pin the "outer container" rectangle without depending on
 * storybook chrome.
 */
import type { Meta, StoryObj } from "@storybook/react";
import React, { useMemo } from "react";
import { DFViewerInfiniteDS } from "../components/BuckarooWidgetInfinite";
import { DFMeta } from "../components/WidgetTypes";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import {
    KeyAwareSmartRowCache,
    PayloadArgs,
    PayloadResponse,
} from "../components/DFViewerParts/SmartRowCache";

// -----------------------------------------------------------------------------
// Synthetic dataframe and cache
// -----------------------------------------------------------------------------
function makeRows(n: number) {
    return Array.from({ length: n }, (_, i) => ({
        index: i,
        a: i * 10,
        b: `row_${i}`,
    }));
}

function makeCache(rowCount: number): KeyAwareSmartRowCache {
    const allData = makeRows(rowCount);
    const cache = new KeyAwareSmartRowCache((pa: PayloadArgs) => {
        const dataEnd = Math.min(pa.end, rowCount);
        if (dataEnd <= pa.start) return;
        const resp: PayloadResponse = {
            key: pa,
            data: allData.slice(pa.start, dataEnd),
            length: rowCount,
        };
        // Async reply mirrors a real server.
        setTimeout(() => cache.addPayloadResponse(resp), 5);
    });
    return cache;
}

function makeDisplayArgs(autoHeight: boolean): Record<string, IDisplayArgs> {
    return {
        main: {
            data_key: "main",
            df_viewer_config: {
                pinned_rows: [],
                left_col_configs: [
                    {
                        col_name: "index",
                        header_name: "index",
                        displayer_args: { displayer: "string" },
                    },
                ],
                column_config: [
                    {
                        col_name: "a",
                        header_name: "a",
                        displayer_args: { displayer: "integer", min_digits: 1, max_digits: 5 },
                    },
                    {
                        col_name: "b",
                        header_name: "b",
                        displayer_args: { displayer: "obj" },
                    },
                ],
                // Mirrors what BuckarooView does in autoHeight mode (#847).
                component_config: autoHeight ? { layoutType: "autoHeight" } : undefined,
            },
            summary_stats_key: "all_stats",
        },
    } as Record<string, IDisplayArgs>;
}

// -----------------------------------------------------------------------------
// BuckarooView-shaped wrapper
// -----------------------------------------------------------------------------
/**
 * Reproduces BuckarooView's wrapper element verbatim so layout effects
 * (the height-100% drop in autoHeight mode) are visible in the rendered
 * DOM. Class name + data attributes match what BuckarooView ships so
 * tests using `.buckaroo_anywidget` work both here and in production.
 */
const BuckarooViewLikeWrapper: React.FC<{
    autoHeight: boolean;
    children: React.ReactNode;
}> = ({ autoHeight, children }) => {
    const wrapperStyle: React.CSSProperties = autoHeight
        ? { width: "100%" }
        : { width: "100%", height: "100%" };
    return (
        <div className="buckaroo_anywidget" style={wrapperStyle} data-testid="bk-wrapper">
            {children}
        </div>
    );
};

const Cell: React.FC<{
    rowCount: number;
    autoHeight: boolean;
    label?: string;
}> = ({ rowCount, autoHeight, label }) => {
    const src = useMemo(() => makeCache(rowCount), [rowCount]);
    const dfMeta: DFMeta = useMemo(
        () => ({
            total_rows: rowCount,
            columns: 2,
            filtered_rows: rowCount,
            rows_shown: rowCount,
        }),
        [rowCount],
    );
    const df_display_args = useMemo(() => makeDisplayArgs(autoHeight), [autoHeight]);
    const df_data_dict = useMemo(() => ({}), []);
    return (
        <BuckarooViewLikeWrapper autoHeight={autoHeight}>
            {label !== undefined ? (
                <div
                    data-testid={`cell-label-${label}`}
                    style={{ fontSize: 11, padding: "2px 6px", color: "#888" }}
                >
                    {label} — {rowCount} rows, autoHeight={String(autoHeight)}
                </div>
            ) : null}
            <DFViewerInfiniteDS
                df_meta={dfMeta}
                df_data_dict={df_data_dict}
                df_display_args={df_display_args}
                src={src}
                df_id={`height-test-${rowCount}-${autoHeight}`}
            />
        </BuckarooViewLikeWrapper>
    );
};

// -----------------------------------------------------------------------------
// Hosts
// -----------------------------------------------------------------------------
const Single: React.FC<{
    rowCount: number;
    autoHeight: boolean;
    hostHeight: number;
}> = ({ rowCount, autoHeight, hostHeight }) => (
    <div
        data-testid="host"
        style={{
            width: 720,
            height: hostHeight,
            border: "2px solid red",
            boxSizing: "border-box",
            overflow: "hidden",
        }}
    >
        <Cell rowCount={rowCount} autoHeight={autoHeight} />
    </div>
);

const Stacked: React.FC<{
    rowCounts: [number, number];
    autoHeight: boolean;
    hostHeight: number;
}> = ({ rowCounts, autoHeight, hostHeight }) => (
    <div
        data-testid="host"
        style={{
            width: 720,
            height: hostHeight,
            border: "2px solid red",
            boxSizing: "border-box",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 8,
            padding: 8,
        }}
    >
        <div data-testid="stack-cell-0" style={{ border: "1px dashed #888" }}>
            <Cell rowCount={rowCounts[0]} autoHeight={autoHeight} label="cell-0" />
        </div>
        <div data-testid="stack-cell-1" style={{ border: "1px dashed #888" }}>
            <Cell rowCount={rowCounts[1]} autoHeight={autoHeight} label="cell-1" />
        </div>
    </div>
);

// -----------------------------------------------------------------------------
// Meta + stories
// -----------------------------------------------------------------------------
const meta: Meta<typeof Single> = {
    title: "Buckaroo/Height/BuckarooView",
    component: Single,
    parameters: { layout: "fullscreen" },
    argTypes: {
        rowCount: { control: { type: "number", min: 1, max: 5000, step: 1 } },
        autoHeight: { control: "boolean" },
        hostHeight: { control: { type: "number", min: 100, max: 2000, step: 10 } },
    },
};
export default meta;

type SingleStory = StoryObj<typeof Single>;

// Tall host (typical browser viewport)
export const SmallDfFixed: SingleStory = {
    args: { rowCount: 3, autoHeight: false, hostHeight: 700 },
};
export const SmallDfAutoHeight: SingleStory = {
    args: { rowCount: 3, autoHeight: true, hostHeight: 700 },
};
export const LargeDfFixed: SingleStory = {
    args: { rowCount: 2000, autoHeight: false, hostHeight: 700 },
};
export const LargeDfAutoHeight: SingleStory = {
    args: { rowCount: 2000, autoHeight: true, hostHeight: 700 },
};

// Short host — caps the host at 400px to exercise the
// short-viewport branch of heightStyle().
export const SmallDfShortHostFixed: SingleStory = {
    args: { rowCount: 3, autoHeight: false, hostHeight: 400 },
};
export const SmallDfShortHostAutoHeight: SingleStory = {
    args: { rowCount: 3, autoHeight: true, hostHeight: 400 },
};
export const LargeDfShortHostFixed: SingleStory = {
    args: { rowCount: 2000, autoHeight: false, hostHeight: 400 },
};
export const LargeDfShortHostAutoHeight: SingleStory = {
    args: { rowCount: 2000, autoHeight: true, hostHeight: 400 },
};

// Stacked — the actual #846/#847 motivating use case.
type StackedArgs = {
    rowCounts: [number, number];
    autoHeight: boolean;
    hostHeight: number;
};
export const StackedAutoHeightSmallLarge: StoryObj<typeof Stacked> = {
    render: (args: StackedArgs) => <Stacked {...args} />,
    args: { rowCounts: [4, 200], autoHeight: true, hostHeight: 900 },
};
export const StackedFixedSmallLarge: StoryObj<typeof Stacked> = {
    render: (args: StackedArgs) => <Stacked {...args} />,
    args: { rowCounts: [4, 200], autoHeight: false, hostHeight: 900 },
};
