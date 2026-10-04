/**
 * Story for the two-message protocol's client states (rows-first c0a).
 *
 * The server sends the first message once the schema and row count are known,
 * and the summary stats later or never. `df_meta.stats.status` says which:
 *
 *   - "pending"      pinned keys with no value show a placeholder row
 *   - "not_computed" pinned keys with no value are omitted
 *   - "complete"     stats are present; also the meaning of a missing
 *                    `df_meta.stats`, as servers without the field send
 *
 * Column `a` is color-mapped and has a simple tooltip, so the story also shows
 * that cells restyle when the histogram bins arrive and that hovering a
 * valueless pinned cell does nothing. Used by stats-pending-pinned-rows.spec.ts.
 */
import type { Meta, StoryObj } from "@storybook/react";
import React, { useMemo, useState } from "react";
import { DFViewerInfiniteDS } from "../components/BuckarooWidgetInfinite";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import { KeyAwareSmartRowCache, PayloadResponse } from "../components/DFViewerParts/SmartRowCache";
import { DFMeta } from "../components/WidgetTypes";

type Status = "pending" | "not_computed" | "complete";
const STATUSES: Status[] = ["pending", "not_computed", "complete"];

const mainData: DFData = [
  { index: 0, a: 1, b: "x" },
  { index: 1, a: 2, b: "y" },
  { index: 2, a: 3, b: "z" },
  { index: 3, a: 4, b: "w" },
  { index: 4, a: 5, b: "v" },
];

const completeStats: DFData = [
  { index: "dtype", a: "int64", b: "object" },
  { index: "mean", a: 3, b: "N/A" },
  { index: "histogram_bins", a: [0, 1, 2, 3, 4, 5], b: [] },
];

const viewerConfig: DFViewerConfig = {
  column_config: [
    {
      col_name: "a",
      header_name: "a",
      displayer_args: { displayer: "obj" },
      color_map_config: { color_rule: "color_map", map_name: "BLUE_TO_YELLOW", val_column: "a" },
      tooltip_config: { tooltip_type: "simple", val_column: "a" },
    },
    { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
  ],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } }],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "mean", displayer_args: { displayer: "obj" } },
  ],
};

const displayArgs: Record<string, IDisplayArgs> = {
  main: { data_key: "main", df_viewer_config: viewerConfig, summary_stats_key: "all_stats" },
};

const StatsPendingPinnedRowsInner: React.FC = () => {
  const [status, setStatus] = useState<Status>("pending");

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

  const df_meta = useMemo(
    () =>
      ({
        total_rows: mainData.length,
        columns: 2,
        filtered_rows: mainData.length,
        rows_shown: mainData.length,
        stats: { status },
      }) as DFMeta,
    [status],
  );
  const df_data_dict = useMemo(
    () => ({
      main: [] as DFData,
      all_stats: status === "complete" ? completeStats : ([] as DFData),
      empty: [] as DFData,
    }),
    [status],
  );

  return (
    <div style={{ width: 720 }}>
      <div style={{ padding: "8px 12px", marginBottom: 8 }}>
        {STATUSES.map((s) => (
          <button key={s} data-testid={`status-${s}`} onClick={() => setStatus(s)} style={{ marginRight: 8 }}>
            {s}
          </button>
        ))}
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>df_meta.stats.status = {status}</span>
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
  component: StatsPendingPinnedRowsInner,
  parameters: { layout: "centered" },
} satisfies Meta<typeof StatsPendingPinnedRowsInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
