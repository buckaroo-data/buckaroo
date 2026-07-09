import type { Meta, StoryObj } from "@storybook/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
 * Linked brushing demo wired through `SelectionBus` — the same bus a real
 * Vega-Lite bridge would publish on. Two `DFViewer` instances subscribe to
 * channel "demo" and one of them publishes on row click. Buttons simulate
 * an external publisher (the role a brushed Vega chart would play).
 *
 * On message, each grid mutates `__selected` on each row via
 * `api.applyTransaction` and calls `api.refreshCells({ force: true })` —
 * no remount, scroll position preserved.
 */

const CHANNEL = "demo";
const HIGHLIGHT = "#ffe680";
const SELECTION_KEY = "id";
const N_ROWS = 100;

const REGIONS = ["North", "South", "East", "West", "Central"];

type Row = {
    index: number;
    id: number;
    region: string;
    revenue: number;
    units: number;
    __selected: 1 | null;
};

function seededRandom(seed: number) {
    let s = seed >>> 0;
    return () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 0xffffffff;
    };
}

const buildRows = (): Row[] => {
    const rand = seededRandom(42);
    return Array.from({ length: N_ROWS }, (_, i) => ({
        index: i,
        id: i,
        region: REGIONS[Math.floor(rand() * REGIONS.length)],
        revenue: Math.round(rand() * 20000 + 1000),
        units: Math.round(rand() * 500 + 10),
        __selected: null as 1 | null,
    }));
};

const BASE_ROWS = buildRows();

const PRESET_SELECTIONS: Record<string, SelectionId[]> = {
    "Top 10 by revenue": [...BASE_ROWS]
        .sort((a, b) => b.revenue - a.revenue)
        .slice(0, 10)
        .map((r) => r.id),
    "Region: North": BASE_ROWS.filter((r) => r.region === "North").map(
        (r) => r.id,
    ),
    "Every 7th row": BASE_ROWS.filter((r) => r.id % 7 === 0).map((r) => r.id),
};

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
            col_name: "region",
            header_name: "Region",
            displayer_args: { displayer: "string" },
            color_map_config: HIGHLIGHT_RULE,
        },
        {
            col_name: "revenue",
            header_name: "Revenue ($)",
            displayer_args: {
                displayer: "float",
                min_fraction_digits: 0,
                max_fraction_digits: 0,
            },
            color_map_config: HIGHLIGHT_RULE,
        },
        {
            col_name: "units",
            header_name: "Units",
            displayer_args: { displayer: "integer", min_digits: 1, max_digits: 4 },
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

/**
 * One grid + the wiring that turns it into a bus participant. Subscribes
 * on mount, mutates rows + refreshes cells on every incoming message,
 * publishes on row click.
 */
const LinkedGrid = ({
    title,
    sourceId,
    onSelectionCount,
}: {
    title: string;
    sourceId: string;
    onSelectionCount?: (n: number) => void;
}) => {
    const bus = useMemo(getSelectionBus, []);
    const apiRef = useRef<GridApi | null>(null);
    const df_viewer_config = useMemo(buildConfig, []);
    const df_data: DFData = useMemo(
        () => BASE_ROWS.map((r) => ({ ...r })),
        [],
    );

    const applySelection = useCallback(
        (ids: SelectionId[]) => {
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
            if (updates.length > 0) {
                api.applyTransaction({ update: updates });
            }
            api.refreshCells({ force: true });
            onSelectionCount?.(idSet.size);
        },
        [onSelectionCount],
    );

    useEffect(() => {
        return bus.subscribe(CHANNEL, (msg) => applySelection(msg.ids), sourceId);
    }, [bus, sourceId, applySelection]);

    const onApiReady = useCallback((api: GridApi) => {
        apiRef.current = api;
        api.addEventListener("rowClicked", (ev: any) => {
            if (!ev.data) return;
            bus.publish(CHANNEL, [ev.data[SELECTION_KEY]], sourceId);
        });
    }, [bus, sourceId]);

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontWeight: 600 }}>{title}</div>
            <div style={{ width: 520, height: 360 }}>
                <DFViewer
                    df_data={df_data}
                    df_viewer_config={df_viewer_config}
                    onGridApiReady={onApiReady}
                />
            </div>
        </div>
    );
};

const LinkedBrushingDemo = () => {
    const bus = useMemo(getSelectionBus, []);
    const [count, setCount] = useState(0);
    const [lastSource, setLastSource] = useState<string>("(none)");

    useEffect(() => {
        return bus.subscribe(CHANNEL, (msg) => {
            setCount(msg.ids.length);
            setLastSource(msg.source);
        });
    }, [bus]);

    const publish = (name: string) => {
        bus.publish(CHANNEL, PRESET_SELECTIONS[name] ?? [], "buttons");
    };

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div
                style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    flexWrap: "wrap",
                }}
            >
                <span style={{ fontWeight: 600 }}>Publish to bus:</span>
                {Object.keys(PRESET_SELECTIONS).map((name) => (
                    <button
                        key={name}
                        onClick={() => publish(name)}
                        style={{
                            padding: "6px 12px",
                            borderRadius: 4,
                            border: "1px solid #888",
                            background: "white",
                            cursor: "pointer",
                        }}
                    >
                        {name}
                    </button>
                ))}
                <button
                    onClick={() => bus.publish(CHANNEL, [], "buttons")}
                    style={{
                        padding: "6px 12px",
                        borderRadius: 4,
                        border: "1px solid #888",
                        background: "white",
                        cursor: "pointer",
                    }}
                >
                    Clear
                </button>
                <span style={{ marginLeft: 8, color: "#666" }}>
                    last: {count} ids from <code>{lastSource}</code>
                </span>
            </div>
            <div style={{ color: "#666", fontSize: 13 }}>
                Both grids subscribe to channel <code>"{CHANNEL}"</code>.
                Click any row in either grid to broadcast a single-id selection;
                the other grid highlights that row. Buttons simulate an
                external publisher (the role a Vega-Lite brush would play).
            </div>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                <LinkedGrid
                    title="Grid A"
                    sourceId="grid-A"
                    onSelectionCount={() => undefined}
                />
                <LinkedGrid title="Grid B" sourceId="grid-B" />
            </div>
        </div>
    );
};

const meta: Meta<typeof LinkedBrushingDemo> = {
    title: "Buckaroo/LinkedBrushing",
    component: LinkedBrushingDemo,
    parameters: { layout: "padded" },
    tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
