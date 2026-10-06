/**
 * Summary stats that arrive after the rows (rows-first c0a).
 *
 * The rows load at once; the summary stats arrive `statsDelayMs` later. Until
 * then each pinned key shows as a placeholder row: its label, empty cells.
 * Column `a` is color-mapped, so its cells restyle when the histogram bins
 * arrive.
 *
 *   - Delayed: the stats arrive on a timer. "Reload" clears them and starts
 *     the timer again; the delay is a control.
 *   - Manual: the stats arrive only on "Deliver stats now". Used by
 *     stats-pending-pinned-rows.spec.ts.
 */
import type { Meta, StoryObj } from "@storybook/react";
import React, { useEffect, useMemo, useState } from "react";
import { DFViewerInfiniteDS } from "../components/BuckarooWidgetInfinite";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import { KeyAwareSmartRowCache, PayloadResponse } from "../components/DFViewerParts/SmartRowCache";
import { DFMeta } from "../components/WidgetTypes";

const N_ROWS = 200;
const COLORS = ["red", "green", "blue", "orange"];

const mainData: DFData = Array.from({ length: N_ROWS }, (_, i) => ({
  index: i,
  a: (i * 37) % 100,
  b: Math.round(((i * 7919) % 1000) / 10) / 10,
  c: COLORS[i % COLORS.length],
}));

const mean = (col: "a" | "b") => mainData.reduce((acc, r) => acc + (r[col] as number), 0) / N_ROWS;

const numericHistogram = [
  { name: "0 - 20", population: 20 },
  { name: "20 - 40", population: 20 },
  { name: "40 - 60", population: 20 },
  { name: "60 - 80", population: 20 },
  { name: "80 - 100", population: 20 },
];
const categoricalHistogram = COLORS.map((name) => ({ name, cat_pop: 25 }));

const completeStats: DFData = [
  { index: "dtype", a: "int64", b: "float64", c: "object" },
  { index: "mean", a: mean("a"), b: mean("b"), c: null },
  { index: "histogram", a: numericHistogram, b: numericHistogram, c: categoricalHistogram },
  { index: "histogram_bins", a: [0, 20, 40, 60, 80, 100], b: [0, 2, 4, 6, 8, 10], c: [] },
];

const floatArgs = { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 2 } as const;

const viewerConfig: DFViewerConfig = {
  column_config: [
    {
      col_name: "a",
      header_name: "a",
      displayer_args: { displayer: "obj" },
      color_map_config: { color_rule: "color_map", map_name: "BLUE_TO_YELLOW", val_column: "a" },
    },
    { col_name: "b", header_name: "b", displayer_args: floatArgs },
    { col_name: "c", header_name: "c", displayer_args: { displayer: "obj" } },
  ],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } }],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "mean", displayer_args: floatArgs },
    { primary_key_val: "histogram", displayer_args: { displayer: "histogram" } },
  ],
};

const displayArgs: Record<string, IDisplayArgs> = {
  main: { data_key: "main", df_viewer_config: viewerConfig, summary_stats_key: "all_stats" },
};

const df_meta: DFMeta = { total_rows: N_ROWS, columns: 3, filtered_rows: N_ROWS, rows_shown: N_ROWS };

interface DelayedStatsProps {
  // How long after the rows the summary stats arrive.
  statsDelayMs: number;
  // false: the stats arrive only when "Deliver stats now" is clicked.
  autoDeliver: boolean;
}

const DelayedStats: React.FC<DelayedStatsProps> = ({ statsDelayMs, autoDeliver }) => {
  const [statsArrived, setStatsArrived] = useState(false);
  const [loads, setLoads] = useState(0);

  useEffect(() => {
    setStatsArrived(false);
    if (!autoDeliver) return;
    const t = setTimeout(() => setStatsArrived(true), statsDelayMs);
    return () => clearTimeout(t);
  }, [statsDelayMs, autoDeliver, loads]);

  const src = useMemo(() => {
    const cache = new KeyAwareSmartRowCache((pa) => {
      const resp: PayloadResponse = {
        key: pa,
        data: mainData.slice(pa.start, Math.min(pa.end, mainData.length)),
        length: mainData.length,
      };
      setTimeout(() => cache.addPayloadResponse(resp), 10);
    });
    return cache;
  }, []);

  const df_data_dict = useMemo(
    () => ({ main: [] as DFData, all_stats: statsArrived ? completeStats : ([] as DFData), empty: [] as DFData }),
    [statsArrived],
  );

  const waiting = autoDeliver ? `waiting (${statsDelayMs} ms)` : "waiting";
  return (
    <div style={{ width: 720 }}>
      <div style={{ padding: "8px 12px", marginBottom: 8, display: "flex", gap: 8, alignItems: "center" }}>
        <button data-testid="reload" onClick={() => setLoads((n) => n + 1)}>Reload</button>
        <button data-testid="deliver-stats" onClick={() => setStatsArrived(true)} disabled={statsArrived}>
          Deliver stats now
        </button>
        <span data-testid="stats-state" style={{ fontFamily: "monospace", fontSize: 12 }}>
          summary stats: {statsArrived ? "arrived" : waiting}
        </span>
      </div>
      <div style={{ height: 400 }}>
        <DFViewerInfiniteDS
          df_meta={df_meta}
          df_data_dict={df_data_dict}
          df_display_args={displayArgs}
          src={src}
          df_id="stats-pending"
        />
      </div>
    </div>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/StatsPendingPinnedRows",
  component: DelayedStats,
  parameters: { layout: "centered" },
  argTypes: {
    statsDelayMs: { control: { type: "range", min: 0, max: 10000, step: 250 } },
  },
} satisfies Meta<typeof DelayedStats>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Delayed: Story = {
  args: { statsDelayMs: 2500, autoDeliver: true },
};

export const Manual: Story = {
  args: { statsDelayMs: 0, autoDeliver: false },
};
