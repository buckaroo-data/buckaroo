/**
 * Story to verify "inherit" displayer on pinned rows.
 *
 * Sets up an integer column (float displayer with 0 fraction digits)
 * and a float column (3 fraction digits), then uses pinned rows with
 * displayer_args: { displayer: "inherit" } for mean, std, min, median, max.
 *
 * Expected: pinned rows use the column's own formatter.
 *   - Integer column: mean=894.8674 renders as "895" (0 decimals)
 *   - Float column:   mean=3.14159  renders as "3.142" (3 decimals)
 */
import type { Meta, StoryObj } from "@storybook/react";
import { useMemo } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { ShadowDomWrapper } from "./StoryUtils";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";

type DFRow = Record<string, any>;

const idxCol: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "obj" },
};

const intCol: NormalColumnConfig = {
  col_name: "station_id",
  header_name: "station_id",
  displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 },
};

const floatCol: NormalColumnConfig = {
  col_name: "temperature",
  header_name: "temperature",
  displayer_args: { displayer: "float", min_fraction_digits: 3, max_fraction_digits: 3 },
};

const viewerConfig: DFViewerConfig = {
  column_config: [intCol, floatCol],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "mean", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "std", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "min", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "median", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "max", displayer_args: { displayer: "inherit" } },
  ],
};

const mainData: DFRow[] = [
  { index: 0, station_id: 519, temperature: 22.5 },
  { index: 1, station_id: 497, temperature: 18.3 },
  { index: 2, station_id: 402, temperature: 25.1 },
  { index: 3, station_id: 435, temperature: 19.8 },
  { index: 4, station_id: 293, temperature: 21.0 },
];

const summaryStats: DFRow[] = [
  { index: "dtype", station_id: "int64", temperature: "float64" },
  { index: "mean", station_id: 894.8674, temperature: 3.14159 },
  { index: "std", station_id: 1052.051, temperature: 1.7321 },
  { index: "min", station_id: 0, temperature: 0.5 },
  { index: "median", station_id: 72, temperature: 2.718 },
  { index: "max", station_id: 3249, temperature: 99.9 },
];

const InheritPinnedRowsInner = () => {
  const data_wrapper = useMemo(
    () => ({
      data_type: "Raw" as const,
      data: mainData,
      length: mainData.length,
    }),
    [],
  );
  return (
    <ShadowDomWrapper>
      <div style={{ height: 500, width: 640 }}>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={viewerConfig}
          summary_stats_data={summaryStats}
          activeCol={["station_id", "station_id"]}
          setActiveCol={() => {}}
          outside_df_params={{}}
        />
      </div>
    </ShadowDomWrapper>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/InheritPinnedRows",
  component: InheritPinnedRowsInner,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof InheritPinnedRowsInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {},
};
