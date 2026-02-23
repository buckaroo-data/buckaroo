/**
 * Edge-case stories for inherit displayer: string columns, NaN values,
 * large numbers, negative numbers, all-identical values.
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

/** Matches Python DefaultMainStyling output for mixed-type DataFrame */
const mixedConfig: DFViewerConfig = {
  column_config: [
    { col_name: "int_col", header_name: "int_col", displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 } },
    { col_name: "float_col", header_name: "float_col", displayer_args: { displayer: "float", min_fraction_digits: 3, max_fraction_digits: 3 } },
    { col_name: "str_col", header_name: "str_col", displayer_args: { displayer: "string", max_length: 35 } },
  ],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "non_null_count", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "null_count", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "mean", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "std", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "min", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "max", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "most_freq", displayer_args: { displayer: "inherit" } },
  ],
};

const mixedSummary: DFRow[] = [
  { index: "dtype", int_col: "int64", float_col: "float64", str_col: "object" },
  { index: "non_null_count", int_col: 3, float_col: 3, str_col: 3 },
  { index: "null_count", int_col: 0, float_col: 0, str_col: 0 },
  { index: "mean", int_col: 2, float_col: 2.5, str_col: null },
  { index: "std", int_col: 1, float_col: 1.0, str_col: null },
  { index: "min", int_col: 1, float_col: 1.5, str_col: "a" },
  { index: "max", int_col: 3, float_col: 3.5, str_col: "c" },
  { index: "most_freq", int_col: 1, float_col: 1.5, str_col: "a" },
];

const MixedTypesInner = () => {
  const data_wrapper = useMemo(() => ({
    data_type: "Raw" as const,
    data: [],
    length: 0,
  }), []);
  return (
    <ShadowDomWrapper>
      <div style={{ height: 500, width: 800 }}>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={mixedConfig}
          summary_stats_data={mixedSummary}
          activeCol={["int_col", "int_col"]}
          setActiveCol={() => {}}
          outside_df_params={{}}
        />
      </div>
    </ShadowDomWrapper>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/InheritEdgeCases",
  component: MixedTypesInner,
  parameters: { layout: "centered" },
} satisfies Meta<typeof MixedTypesInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const MixedTypes: Story = { args: {} };

/** Extreme numbers: large values, tiny floats, negatives */
const extremeConfig: DFViewerConfig = {
  column_config: [
    { col_name: "large", header_name: "large", displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 } },
    { col_name: "small", header_name: "small", displayer_args: { displayer: "float", min_fraction_digits: 3, max_fraction_digits: 3 } },
    { col_name: "negative", header_name: "negative", displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 } },
  ],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "non_null_count", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "mean", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "std", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "min", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "max", displayer_args: { displayer: "inherit" } },
  ],
};

const extremeSummary: DFRow[] = [
  { index: "dtype", large: "int64", small: "float64", negative: "int64" },
  { index: "non_null_count", large: 3, small: 3, negative: 3 },
  { index: "mean", large: 2000000, small: 0.002, negative: -200 },
  { index: "std", large: 1000000, small: 0.001, negative: 100 },
  { index: "min", large: 1000000, small: 0.001, negative: -300 },
  { index: "max", large: 3000000, small: 0.003, negative: -100 },
];

const ExtremeNumbersInner = () => {
  const data_wrapper = useMemo(() => ({
    data_type: "Raw" as const,
    data: [],
    length: 0,
  }), []);
  return (
    <ShadowDomWrapper>
      <div style={{ height: 500, width: 800 }}>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={extremeConfig}
          summary_stats_data={extremeSummary}
          activeCol={["large", "large"]}
          setActiveCol={() => {}}
          outside_df_params={{}}
        />
      </div>
    </ShadowDomWrapper>
  );
};

export const ExtremeNumbers: Story = {
  render: () => <ExtremeNumbersInner />,
};
