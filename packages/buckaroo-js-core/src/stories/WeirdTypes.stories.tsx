import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { DFData, DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { DFViewer } from "../components/DFViewerParts/DFViewerInfinite";
import "../style/dcf-npm.css";

const DFViewerWrap = ({
  df_data,
  df_viewer_config,
  summary_stats_data,
}: {
  df_data: DFData;
  df_viewer_config: DFViewerConfig;
  summary_stats_data?: DFData;
}) => {
  const [activeCol, setActiveCol] = useState<[string, string]>(["a", "a"]);
  return (
    <div style={{ height: 500, width: 1200 }}>
      <DFViewer
        df_data={df_data}
        df_viewer_config={df_viewer_config}
        summary_stats_data={summary_stats_data}
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

// Histogram data matching what Python produces for categorical columns
const categoricalHistogram = [
  { name: "red", cat_pop: 40.0 },
  { name: "green", cat_pop: 40.0 },
  { name: "blue", cat_pop: 20.0 },
];

const numericHistogram = [
  { name: "0 - 10", tail: 1 },
  { name: "10-20", population: 25.0 },
  { name: "20-30", population: 25.0 },
  { name: "30-40", population: 25.0 },
  { name: "40-50", population: 25.0 },
  { name: "50+", tail: 1 },
];

const durationHistogram = [
  { name: "100µs", cat_pop: 20.0 },
  { name: "1ms", cat_pop: 20.0 },
  { name: "1s", cat_pop: 20.0 },
  { name: "1d", cat_pop: 20.0 },
  { name: "365d", cat_pop: 20.0 },
];

const periodHistogram = [
  { name: "2021-01", cat_pop: 20.0 },
  { name: "2021-02", cat_pop: 20.0 },
  { name: "2021-03", cat_pop: 20.0 },
  { name: "2021-04", cat_pop: 20.0 },
  { name: "2021-05", cat_pop: 20.0 },
];

const intervalHistogram = [
  { name: "(0, 1]", cat_pop: 20.0 },
  { name: "(1, 2]", cat_pop: 20.0 },
  { name: "(2, 3]", cat_pop: 20.0 },
  { name: "(3, 4]", cat_pop: 20.0 },
  { name: "(4, 5]", cat_pop: 20.0 },
];

// Data matching what Python serializes for the weird types DataFrame.
const weirdTypesData: DFData = [
  { index: 0, a: "red",   b: "P1DT2H3M4S",       c: "2021-01", d: "(0, 1]", e: 10 },
  { index: 1, a: "green", b: "P0DT0H0M1S",        c: "2021-02", d: "(1, 2]", e: 20 },
  { index: 2, a: "blue",  b: "P365DT0H0M0S",      c: "2021-03", d: "(2, 3]", e: 30 },
  { index: 3, a: "red",   b: "P0DT0H0M0.001S",    c: "2021-04", d: "(3, 4]", e: 40 },
  { index: 4, a: "green", b: "P0DT0H0M0.0001S",   c: "2021-05", d: "(4, 5]", e: 50 },
];

const weirdTypesSummaryStats: DFData = [
  { index: "dtype", a: "category", b: "timedelta64[ns]", c: "period[M]", d: "interval[int64, right]", e: "int64" },
  { index: "histogram", a: categoricalHistogram, b: durationHistogram, c: periodHistogram, d: intervalHistogram, e: numericHistogram },
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
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "histogram", displayer_args: { displayer: "histogram" } },
  ],
  left_col_configs: [INDEX_COL],
};

export const PandasWeirdTypes: Story = {
  args: {
    df_data: weirdTypesData,
    df_viewer_config: weirdTypesConfig,
    summary_stats_data: weirdTypesSummaryStats,
  },
};

// Polars weird types
const polarsWeirdTypesData: DFData = [
  { index: 0, a: "P0DT0H0M0.1S",       b: "14:30:00",  c: "red",   d: 100.5,    e: "68656c6c6f", f: 10 },
  { index: 1, a: "P0DT1H2M3S",          b: "09:15:30",  c: "green", d: 200.75,   e: "776f726c64", f: 20 },
  { index: 2, a: "P1DT0H0M0S",          b: "00:00:01",  c: "blue",  d: 0.01,     e: "000102",     f: 30 },
  { index: 3, a: "P0DT0H0M0.0000005S",  b: "23:59:59",  c: "red",   d: 99999.99, e: "74657374",   f: 40 },
  { index: 4, a: "P0DT0H1M0S",          b: "12:00:00",  c: "green", d: 3.14,     e: "fffe",       f: 50 },
];

const timeHistogram = [
  { name: "00:00:01", cat_pop: 20.0 },
  { name: "09:15:30", cat_pop: 20.0 },
  { name: "12:00:00", cat_pop: 20.0 },
  { name: "14:30:00", cat_pop: 20.0 },
  { name: "23:59:59", cat_pop: 20.0 },
];

const decimalHistogram = [
  { name: "0.01 - 3.14", tail: 1 },
  { name: "3-100", population: 33.0 },
  { name: "100-200", population: 33.0 },
  { name: "200-99999", population: 33.0 },
  { name: "99999.99+", tail: 1 },
];

const polarsSummaryStats: DFData = [
  { index: "dtype", a: "Duration(time_unit='us')", b: "Time", c: "Categorical", d: "Decimal(precision=10, scale=2)", e: "Binary", f: "Int64" },
  { index: "histogram", a: durationHistogram, b: timeHistogram, c: categoricalHistogram, d: decimalHistogram, e: categoricalHistogram, f: numericHistogram },
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
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "histogram", displayer_args: { displayer: "histogram" } },
  ],
  left_col_configs: [INDEX_COL],
};

export const PolarsWeirdTypes: Story = {
  args: {
    df_data: polarsWeirdTypesData,
    df_viewer_config: polarsWeirdTypesConfig,
    summary_stats_data: polarsSummaryStats,
  },
};
