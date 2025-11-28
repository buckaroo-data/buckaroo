/*
  Goal of this story:
  - Simulate how outside_df_params affects which dataset is returned by the datasource.
  - Toggling "Toggle Params" flips outside_df_params.key between "A" and "B".
  - Expected: visible rows in the grid switch from A* values to B* values (and vice versa).
  - Failure (symptom of stale state/keying):
    - Rows do not change after toggling (e.g., still show A1/A), which suggests either:
      1) getRowId does not incorporate outside_df_params, so AG Grid reuses old rows, or
      2) the datasource/cache is being queried with a stale key that ignores the updated outside_df_params.
*/
import type { Meta, StoryObj } from "@storybook/react";
import React, { useMemo, useState } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { IDatasource, IGetRowsParams } from "@ag-grid-community/core";

const makeContextualDatasource = (dataA: any[], dataB: any[], delayMs = 0): IDatasource => {
  const total = Math.max(dataA.length, dataB.length);
  return {
    rowCount: total,
    getRows(params: IGetRowsParams) {
      const key = JSON.stringify(params.context?.outside_df_params);
      const useB = key?.includes('"key":"B"');
      const src = useB ? dataB : dataA;
      const slice = src.slice(params.startRow, params.endRow);
      if (delayMs > 0) {
        setTimeout(() => params.successCallback(slice, src.length), delayMs);
      } else {
        params.successCallback(slice, src.length);
      }
    },
  };
};

const wrapDatasource = (ds: IDatasource, length: number) => ({
  datasource: ds,
  data_type: "DataSource" as const,
  length,
});

const twoColConfig: DFViewerConfig = {
  column_config: [
    { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
    { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
  ],
  pinned_rows: [],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "string" } }],
};

const dataA = [
  { a: "A1", b: "A" },
  { a: "A2", b: "A" },
  { a: "A3", b: "A" },
];
const dataB = [
  { a: "B1", b: "B" },
  { a: "B2", b: "B" },
  { a: "B3", b: "B" },
];

const Outer: React.FC<{ delayed?: boolean }> = ({ delayed }) => {
  const [outside, setOutside] = useState<{ key: "A" | "B" }>({ key: "A" });
  const ds = useMemo(
    () => makeContextualDatasource(dataA, dataB, delayed ? 150 : 0),
    [delayed]
  );
  const data_wrapper = useMemo(() => wrapDatasource(ds, Math.max(dataA.length, dataB.length)), [ds]);
  return (
    <div style={{ height: 420, width: 520 }}>
      <div style={{ marginBottom: 8, display: "flex", gap: 8 }}>
        <button onClick={() => setOutside(o => ({ key: o.key === "A" ? "B" : "A" }))}>
          Toggle Params
        </button>
        <span>outside_df_params.key = {outside.key}</span>
      </div>
      <DFViewerInfinite
        data_wrapper={data_wrapper}
        df_viewer_config={twoColConfig}
        summary_stats_data={[]}
        outside_df_params={outside}
        activeCol={["", ""]}
        setActiveCol={() => {}}
        error_info={""}
      />
    </div>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/OutsideParamsInconsistency",
  component: Outer,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Outer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: { delayed: false },
};

export const WithDelay: Story = {
  args: { delayed: true },
};


