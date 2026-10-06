import type { Meta, StoryObj } from "@storybook/react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { GridApi } from "ag-grid-community";

import "../style/dcf-npm.css";
import { DFViewer } from "../components/DFViewerParts/DFViewerInfinite";
import {
    ColumnConfig,
    DFData,
    DFViewerConfig,
} from "../components/DFViewerParts/DFWhole";
import {
    SelectionId,
    getSelectionBus,
} from "../selection/SelectionBus";

/**
 * Linked brushing between a Vega-Lite scatterplot and a Buckaroo
 * `DFViewer`, communicating through the same `SelectionBus` used by the
 * pure-DFViewer demo. Vega-Lite is loaded with a dynamic `import()` so it
 * is not part of the buckaroo-js-core bundle — bundlers code-split this
 * chunk and only fetch it when this story is rendered. In production,
 * `vega-embed` would be a peer / optional dependency: consumers who want
 * the bridge install it themselves.
 *
 * Brush the chart → buckaroo highlights the brushed ids.
 * Click a buckaroo row → the chart highlights that point.
 */

const CHANNEL = "vega-demo";
const HIGHLIGHT = "#ffe680";
const SELECTION_KEY = "id";
const N_ROWS = 100;

type Row = {
    index: number;
    id: number;
    x: number;
    y: number;
    cat: string;
    __selected: 1 | null;
};

function seededRandom(seed: number) {
    let s = seed >>> 0;
    return () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 0xffffffff;
    };
}

const CATS = ["alpha", "beta", "gamma", "delta"];

const BASE_ROWS: Row[] = (() => {
    const rand = seededRandom(7);
    return Array.from({ length: N_ROWS }, (_, i) => ({
        index: i,
        id: i,
        x: Math.round(rand() * 1000) / 10,
        y: Math.round(rand() * 1000) / 10,
        cat: CATS[Math.floor(rand() * CATS.length)],
        __selected: null as 1 | null,
    }));
})();

const HIGHLIGHT_RULE = {
    color_rule: "color_not_null" as const,
    conditional_color: HIGHLIGHT,
    exist_column: "__selected",
};

const buildConfig = (): DFViewerConfig => {
    const column_config: ColumnConfig[] = [
        {
            col_name: "id",
            header_name: "id",
            displayer_args: { displayer: "integer", min_digits: 1, max_digits: 4 },
            color_map_config: HIGHLIGHT_RULE,
        },
        {
            col_name: "cat",
            header_name: "Category",
            displayer_args: { displayer: "string" },
            color_map_config: HIGHLIGHT_RULE,
        },
        {
            col_name: "x",
            header_name: "x",
            displayer_args: {
                displayer: "float",
                min_fraction_digits: 1,
                max_fraction_digits: 1,
            },
            color_map_config: HIGHLIGHT_RULE,
        },
        {
            col_name: "y",
            header_name: "y",
            displayer_args: {
                displayer: "float",
                min_fraction_digits: 1,
                max_fraction_digits: 1,
            },
            color_map_config: HIGHLIGHT_RULE,
        },
    ];
    return {
        column_config,
        pinned_rows: [],
        left_col_configs: [
            {
                col_name: "index",
                header_name: "#",
                displayer_args: { displayer: "string" },
            },
        ],
    };
};

const BUCKAROO_SOURCE = "vega-demo-buckaroo";
const VEGA_SOURCE = "vega-demo-chart";
const BRUSH_NAME = "brush";

const vegaSpec = {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    width: 420,
    height: 360,
    data: { values: BASE_ROWS },
    params: [
        {
            name: BRUSH_NAME,
            select: { type: "interval", encodings: ["x", "y"] },
        },
    ],
    mark: { type: "circle", size: 80 },
    encoding: {
        x: { field: "x", type: "quantitative" },
        y: { field: "y", type: "quantitative" },
        color: {
            condition: { param: BRUSH_NAME, field: "cat", type: "nominal" },
            value: "lightgray",
        },
        tooltip: [
            { field: "id" },
            { field: "cat" },
            { field: "x" },
            { field: "y" },
        ],
    },
};

const VegaChart = () => {
    const hostRef = useRef<HTMLDivElement | null>(null);
    const bus = useMemo(getSelectionBus, []);

    useEffect(() => {
        let cancelled = false;
        let view: any = null;
        let unsub: (() => void) | null = null;

        // Dynamic import keeps vega-embed out of the buckaroo-js-core bundle.
        // The chunk only loads when this story is rendered.
        import("vega-embed").then(({ default: embed }) => {
            if (cancelled || !hostRef.current) return;
            embed(hostRef.current, vegaSpec as any, { actions: false }).then(
                (result) => {
                    if (cancelled) return;
                    view = result.view;

                    // Vega → bus: on every brush change, look up the data
                    // contained in the brush region and publish their ids.
                    view.addSignalListener(BRUSH_NAME, (_n: string, value: any) => {
                        // vega-lite interval selection signal materializes
                        // as { x: [x0, x1], y: [y0, y1] } once the user has
                        // drawn a rectangle; it is `{}` or undefined while
                        // the brush is cleared.
                        const xRange: [number, number] | undefined = value?.x;
                        const yRange: [number, number] | undefined = value?.y;
                        if (!xRange && !yRange) {
                            bus.publish(CHANNEL, [], VEGA_SOURCE);
                            return;
                        }
                        const inBrush = (view.data("source_0") as Row[]).filter(
                            (d) => {
                                const xOk = xRange
                                    ? d.x >= xRange[0] && d.x <= xRange[1]
                                    : true;
                                const yOk = yRange
                                    ? d.y >= yRange[0] && d.y <= yRange[1]
                                    : true;
                                return xOk && yOk;
                            },
                        );
                        bus.publish(
                            CHANNEL,
                            inBrush.map((d) => d.id),
                            VEGA_SOURCE,
                        );
                    });

                    // Bus → Vega: incoming selection becomes a highlight
                    // overlay on top of the brush layer. We do it by
                    // tweaking the dataset rather than the brush param so
                    // remote selections don't fight the user's drag.
                    unsub = bus.subscribe(
                        CHANNEL,
                        (msg) => {
                            const ids = new Set<SelectionId>(msg.ids);
                            const updated = (view.data("source_0") as Row[]).map(
                                (d) => ({
                                    ...d,
                                    __selected: ids.has(d.id) ? 1 : null,
                                }),
                            );
                            view.change(
                                "source_0",
                                (view as any).changeset().remove(() => true).insert(updated),
                            ).run();
                        },
                        VEGA_SOURCE,
                    );
                },
            );
        });

        return () => {
            cancelled = true;
            unsub?.();
            view?.finalize?.();
        };
    }, [bus]);

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontWeight: 600 }}>Vega-Lite scatter (brushable)</div>
            <div ref={hostRef} />
        </div>
    );
};

const BuckarooGrid = () => {
    const bus = useMemo(getSelectionBus, []);
    const apiRef = useRef<GridApi | null>(null);
    const df_viewer_config = useMemo(buildConfig, []);
    const df_data: DFData = useMemo(() => BASE_ROWS.map((r) => ({ ...r })), []);

    const applySelection = useCallback((ids: SelectionId[]) => {
        const api = apiRef.current;
        if (!api) return;
        const idSet = new Set<SelectionId>(ids);
        const updates: Row[] = [];
        api.forEachNode((node) => {
            if (!node.data) return;
            const wanted: 1 | null = idSet.has(node.data[SELECTION_KEY])
                ? 1
                : null;
            if (node.data.__selected !== wanted) {
                updates.push({ ...node.data, __selected: wanted });
            }
        });
        if (updates.length > 0) api.applyTransaction({ update: updates });
        api.refreshCells({ force: true });
    }, []);

    useEffect(() => {
        return bus.subscribe(
            CHANNEL,
            (msg) => applySelection(msg.ids),
            BUCKAROO_SOURCE,
        );
    }, [bus, applySelection]);

    const onApiReady = useCallback(
        (api: GridApi) => {
            apiRef.current = api;
            api.addEventListener("rowClicked", (ev: any) => {
                if (!ev.data) return;
                bus.publish(
                    CHANNEL,
                    [ev.data[SELECTION_KEY]],
                    BUCKAROO_SOURCE,
                );
            });
        },
        [bus],
    );

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontWeight: 600 }}>Buckaroo DFViewer</div>
            <div style={{ width: 560, height: 360 }}>
                <DFViewer
                    df_data={df_data}
                    df_viewer_config={df_viewer_config}
                    onGridApiReady={onApiReady}
                />
            </div>
        </div>
    );
};

const LinkedBrushingVegaDemo = () => {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ color: "#666", fontSize: 13 }}>
                Both views subscribe to channel <code>"{CHANNEL}"</code> on the
                shared <code>SelectionBus</code>. Drag a rectangle on the
                scatter to brush; the grid highlights the brushed ids. Click a
                row in the grid; the chart re-renders with that point flagged.
                Vega-Lite is loaded via dynamic <code>import()</code> — it is
                a devDependency of this story, not a bundled dependency of
                buckaroo-js-core.
            </div>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
                <VegaChart />
                <BuckarooGrid />
            </div>
        </div>
    );
};

const meta: Meta<typeof LinkedBrushingVegaDemo> = {
    title: "Buckaroo/LinkedBrushingVega",
    component: LinkedBrushingVegaDemo,
    parameters: { layout: "padded" },
    tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
