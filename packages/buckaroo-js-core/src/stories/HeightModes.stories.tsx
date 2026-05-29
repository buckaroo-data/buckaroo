/**
 * Buckaroo height modes.
 *
 * The **red border** marks the outer boundary of each embed. Height is
 * controlled at two levels:
 *
 * - **Outer container** (red border) — the footprint of the widget in your page.
 *   For `autoHeight` mode it can be left unsized; for `normal` mode set it to
 *   match `dfvHeight`.
 * - **`component_config.dfvHeight`** — pixel height of the AG Grid viewport.
 *   Defaults to `window.innerHeight / (height_fraction || 2)`.
 *
 * Multiple widgets can share the same DOM without iframes or a server —
 * each is an independent React subtree backed by its own data source.
 */
import type { Meta, StoryObj } from "@storybook/react";
import { useCallback } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import {
    ComponentConfig,
    DFData,
    DFViewerConfig,
    PinnedRowConfig,
} from "../components/DFViewerParts/DFWhole";
import { DatasourceOrRaw } from "../components/DFViewerParts/DFViewerDataHelper";
import { SetColumnFunc } from "../components/DFViewerParts/gridUtils";

// ─── data ────────────────────────────────────────────────────────────────────

const FIVE_ROW_DATA: DFData = [
    { index: 0, name: "Alice", value: 42.5 },
    { index: 1, name: "Bob", value: 73.1 },
    { index: 2, name: "Charlie", value: 19.8 },
    { index: 3, name: "Diana", value: 88.0 },
    { index: 4, name: "Eve", value: 55.3 },
];

const FIVE_HUNDRED_ROW_DATA: DFData = Array.from({ length: 500 }, (_, i) => ({
    index: i,
    name: `row_${String(i).padStart(3, "0")}`,
    value: parseFloat((Math.sin(i * 0.1) * 100).toFixed(2)),
}));

const STAT_NAMES = ["dtype", "count", "unique", "mean", "std", "min", "25%", "50%", "75%", "max"];
const TEN_PINNED_STATS: DFData = STAT_NAMES.map((stat) => ({
    index: stat,
    name: stat === "dtype" ? "object" : "—",
    value: stat === "dtype" ? "float64" : stat === "count" ? 500 : "—",
}));
const TEN_PINNED: PinnedRowConfig[] = STAT_NAMES.map((stat) => ({
    primary_key_val: stat,
    displayer_args: { displayer: "obj" as const },
}));

// ─── helpers ─────────────────────────────────────────────────────────────────

function makeRaw(data: DFData): DatasourceOrRaw {
    return { data_type: "Raw", data, length: data.length };
}

function makeConfig(
    pinnedRows: PinnedRowConfig[] = [],
    compConfig?: ComponentConfig,
): DFViewerConfig {
    return {
        column_config: [
            {
                col_name: "name",
                header_name: "Name",
                displayer_args: { displayer: "obj" as const },
            },
            {
                col_name: "value",
                header_name: "Value",
                displayer_args: {
                    displayer: "float" as const,
                    min_fraction_digits: 1,
                    max_fraction_digits: 2,
                },
            },
        ],
        pinned_rows: pinnedRows,
        left_col_configs: [
            {
                col_name: "index",
                header_name: "#",
                displayer_args: { displayer: "obj" as const },
            },
        ],
        component_config: compConfig,
    };
}

// ─── wrapper component ───────────────────────────────────────────────────────

/**
 * Thin wrapper used by the height-mode stories. The red border marks the outer
 * boundary of the embed. `outerHeight` sets that boundary in pixels; omit it
 * to let `autoHeight` mode size to content.
 */
const HeightExampleWrap = ({
    data_wrapper,
    df_viewer_config,
    summary_stats_data,
    outerHeight,
}: {
    data_wrapper: DatasourceOrRaw;
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: DFData;
    /** Outer container height in px. Omit for autoHeight stories. */
    outerHeight?: number;
}) => {
    const noop = useCallback<SetColumnFunc>(() => {}, []);
    return (
        <div
            style={{
                border: "3px solid red",
                width: 800,
                height: outerHeight,
                boxSizing: "border-box",
            }}
        >
            <DFViewerInfinite
                data_wrapper={data_wrapper}
                df_viewer_config={df_viewer_config}
                summary_stats_data={summary_stats_data}
                setActiveCol={noop}
            />
        </div>
    );
};

// ─── meta ─────────────────────────────────────────────────────────────────────

const meta = {
    title: "Docs/Height Modes",
    component: HeightExampleWrap,
    parameters: { layout: "centered" },
    tags: ["autodocs"],
    argTypes: {
        // suppress complex object controls — only outerHeight is user-adjustable
        data_wrapper: { control: false },
        df_viewer_config: { control: false },
        summary_stats_data: { control: false },
        outerHeight: { control: { type: "number" }, description: "Outer container height (px)" },
    },
} satisfies Meta<typeof HeightExampleWrap>;

export default meta;
type Story = StoryObj<typeof meta>;

// ─── stories ──────────────────────────────────────────────────────────────────

/**
 * 5 rows fit without scrolling, so Buckaroo auto-detects `shortMode` and
 * switches to `domLayout: "autoHeight"`. The grid and outer container grow to
 * content height — no explicit sizing needed.
 */
export const FiveRows: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_ROW_DATA),
        df_viewer_config: makeConfig(),
    },
};

/**
 * Pinned rows count toward the `shortMode` threshold. 10 pinned stat rows +
 * 5 data rows still fit without scrolling, so `autoHeight` is still
 * auto-detected. Pinned rows appear above the scrollable data area.
 */
export const FiveRowsTenPinned: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_ROW_DATA),
        df_viewer_config: makeConfig(TEN_PINNED),
        summary_stats_data: TEN_PINNED_STATS,
    },
};

/**
 * 500 rows exceed the scroll threshold, so Buckaroo switches to
 * `domLayout: "normal"` with a fixed height. Here `dfvHeight: 400` is set
 * explicitly and the outer container matches.
 */
export const FiveHundredRows: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
        df_viewer_config: makeConfig([], { dfvHeight: 400 }),
        outerHeight: 400,
    },
};

/**
 * 500 rows in `normal` mode with 10 stat rows pinned to the top of the grid.
 * Pinned rows stay visible while data rows scroll beneath them.
 */
export const FiveHundredRowsTenPinned: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
        df_viewer_config: makeConfig(TEN_PINNED, { dfvHeight: 400 }),
        summary_stats_data: TEN_PINNED_STATS,
        outerHeight: 400,
    },
};

/**
 * `component_config.dfvHeight` sets an explicit pixel height for the grid,
 * overriding the default of `window.innerHeight / 2`. Set the outer container
 * to the same value. Here `dfvHeight: 200` makes a compact embed.
 */
export const ExplicitHeight200: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
        df_viewer_config: makeConfig([], { dfvHeight: 200 }),
        outerHeight: 200,
    },
};

/**
 * `component_config.height_fraction = 4` sets `dfvHeight = window.innerHeight / 4`.
 * The grid height tracks the browser window — resize to see it update.
 */
export const HeightFraction4: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
        df_viewer_config: makeConfig([], { height_fraction: 4 }),
        outerHeight: 300,
    },
};

/**
 * `component_config.layoutType: "autoHeight"` forces the grid to grow to all
 * rows regardless of count. Use only in hosts where vertical space is
 * unconstrained (e.g. a notebook-style cell stack).
 */
export const ForceAutoHeight: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
        df_viewer_config: makeConfig([], { layoutType: "autoHeight" }),
    },
};

/**
 * `component_config.layoutType: "normal"` forces a fixed-height grid even for
 * small datasets. Useful for fixed-height panels (e.g. an entry-detail sidebar)
 * where the embed must not resize with the data. See also the `autoHeight` prop
 * on `BuckarooServerView` / `DFViewerInfiniteDS`, fixed in #862.
 */
export const ForceNormal: Story = {
    args: {
        data_wrapper: makeRaw(FIVE_ROW_DATA),
        df_viewer_config: makeConfig([], { layoutType: "normal", dfvHeight: 300 }),
        outerHeight: 300,
    },
};
