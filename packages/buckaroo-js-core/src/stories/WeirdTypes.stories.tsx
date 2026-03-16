import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { DFData, DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { SetColumnFunc } from "../components/DFViewerParts/gridUtils";
import { DFViewer } from "../components/DFViewerParts/DFViewerInfinite";
import "../style/dcf-npm.css";

const DFViewerWrap = ({
  df_data,
  df_viewer_config,
}: {
  df_data: DFData;
  df_viewer_config: DFViewerConfig;
}) => {
  const [activeCol, setActiveCol] = useState<[string, string]>(["a", "a"]);
  return (
    <div style={{ height: 500, width: 1200 }}>
      <DFViewer
        df_data={df_data}
        df_viewer_config={df_viewer_config}
        activeCol={activeCol}
        setActiveCol={setActiveCol}
      />
    </div>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/WeirdTypes",
  component: DFViewerWrap,
  parameters: { layout: "centered" },
} satisfies Meta<typeof DFViewerWrap>;

export default meta;
type Story = StoryObj<typeof meta>;

const INDEX_COL: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "string" },
};

// Data matching what Python serializes for the weird types DataFrame.
// JSON path: pd_to_obj produces ISO 8601 durations, string periods/intervals.
// Parquet path: to_parquet converts period/interval/timedelta to str() first.
const weirdTypesData: DFData = [
  { index: 0, a: "red",   b: "P1DT2H3M4S",       c: "2021-01", d: "(0, 1]", e: 10 },
  { index: 1, a: "green", b: "P0DT0H0M1S",        c: "2021-02", d: "(1, 2]", e: 20 },
  { index: 2, a: "blue",  b: "P365DT0H0M0S",      c: "2021-03", d: "(2, 3]", e: 30 },
  { index: 3, a: "red",   b: "P0DT0H0M0.001S",    c: "2021-04", d: "(3, 4]", e: 40 },
  { index: 4, a: "green", b: "P0DT0H0M0.0001S",   c: "2021-05", d: "(4, 5]", e: 50 },
];

const weirdTypesConfig: DFViewerConfig = {
  column_config: [
    { col_name: "a", header_name: "categorical",
      displayer_args: { displayer: "string", max_length: 35 } },
    { col_name: "b", header_name: "timedelta",
      displayer_args: { displayer: "duration" } },
    { col_name: "c", header_name: "period",
      displayer_args: { displayer: "string", max_length: 20 } },
    { col_name: "d", header_name: "interval",
      displayer_args: { displayer: "string", max_length: 35 } },
    { col_name: "e", header_name: "int_col",
      displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 } },
  ],
  pinned_rows: [],
  left_col_configs: [INDEX_COL],
};

export const PandasWeirdTypes: Story = {
  args: {
    df_data: weirdTypesData,
    df_viewer_config: weirdTypesConfig,
  },
};

// Polars weird types — data as it arrives from pl→pd→JSON serialization
const polarsWeirdTypesData: DFData = [
  { index: 0, a: "P0DT0H0M0.1S",       b: "14:30:00",  c: "red",   d: 100.5,    e: "hello", f: 10 },
  { index: 1, a: "P0DT1H2M3S",          b: "09:15:30",  c: "green", d: 200.75,   e: "world", f: 20 },
  { index: 2, a: "P1DT0H0M0S",          b: "00:00:01",  c: "blue",  d: 0.01,     e: "test",  f: 30 },
  { index: 3, a: "P0DT0H0M0.0000005S",  b: "23:59:59",  c: "red",   d: 99999.99, e: "data",  f: 40 },
  { index: 4, a: "P0DT0H1M0S",          b: "12:00:00",  c: "green", d: 3.14,     e: "bytes", f: 50 },
];

const polarsWeirdTypesConfig: DFViewerConfig = {
  column_config: [
    { col_name: "a", header_name: "duration",
      displayer_args: { displayer: "duration" } },
    { col_name: "b", header_name: "time",
      displayer_args: { displayer: "string", max_length: 20 } },
    { col_name: "c", header_name: "categorical",
      displayer_args: { displayer: "string", max_length: 35 } },
    { col_name: "d", header_name: "decimal",
      displayer_args: { displayer: "float", min_fraction_digits: 3, max_fraction_digits: 3 } },
    { col_name: "e", header_name: "binary",
      displayer_args: { displayer: "obj" } },
    { col_name: "f", header_name: "int_col",
      displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 } },
  ],
  pinned_rows: [],
  left_col_configs: [INDEX_COL],
};

export const PolarsWeirdTypes: Story = {
  args: {
    df_data: polarsWeirdTypesData,
    df_viewer_config: polarsWeirdTypesConfig,
  },
};
