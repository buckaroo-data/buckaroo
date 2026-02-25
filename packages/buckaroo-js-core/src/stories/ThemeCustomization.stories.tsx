import type { Meta, StoryObj } from "@storybook/react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFViewerConfig, NormalColumnConfig, ThemeConfig } from "../components/DFViewerParts/DFWhole";
import { SetColumnFunc } from "../components/DFViewerParts/gridUtils";
import { DatasourceOrRaw } from "../components/DFViewerParts/DFViewerDataHelper";

const DFViewerInfiniteWrap = ({
    data_wrapper,
    df_viewer_config,
}: {
    data_wrapper: DatasourceOrRaw;
    df_viewer_config: DFViewerConfig;
}) => {
  const defaultSetColumnFunc = (newCol:[string, string]):void => {
    console.log("defaultSetColumnFunc", newCol)
  }
  const sac:SetColumnFunc = defaultSetColumnFunc;

  return (
     <div style={{height:500, width:800}}>
      <DFViewerInfinite
        data_wrapper={data_wrapper}
        df_viewer_config={df_viewer_config}
        setActiveCol={sac}
      />
     </div>);
}

const meta = {
  title: "Buckaroo/Theme/ThemeCustomization",
  component: DFViewerInfiniteWrap,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {},
} satisfies Meta<typeof DFViewerInfiniteWrap>;

export default meta;
type Story = StoryObj<typeof meta>;

const INDEX_COL_CONFIG: NormalColumnConfig = {
  col_name: 'index',
  header_name: 'index',
  displayer_args: { displayer: 'string' },
};

const left_col_configs = [INDEX_COL_CONFIG];

const sampleData = [
  { index: "0", a: 10, b: "foo", c: 100 },
  { index: "1", a: 20, b: "bar", c: 200 },
  { index: "2", a: 30, b: "baz", c: 300 },
  { index: "3", a: 40, b: "qux", c: 400 },
  { index: "4", a: 50, b: "quux", c: 500 },
];

const rawData: DatasourceOrRaw = {
  data_type: "Raw",
  data: sampleData,
  length: sampleData.length,
};

const baseColumnConfig: NormalColumnConfig[] = [
  { col_name: 'a', header_name: 'a', displayer_args: { displayer: 'integer', min_digits: 1, max_digits: 5 } },
  { col_name: 'b', header_name: 'b', displayer_args: { displayer: 'obj' } },
  { col_name: 'c', header_name: 'c', displayer_args: { displayer: 'integer', min_digits: 1, max_digits: 5 } },
];

function makeConfig(theme?: ThemeConfig): DFViewerConfig {
  return {
    column_config: baseColumnConfig,
    pinned_rows: [],
    left_col_configs,
    component_config: theme ? { theme } : undefined,
  };
}

export const DefaultNoTheme: Story = {
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig(),
  },
};

export const CustomAccent: Story = {
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      accentColor: '#ff6600',
    }),
  },
};

export const ForcedDark: Story = {
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      colorScheme: 'dark',
      backgroundColor: '#1a1a2e',
    }),
  },
};

export const ForcedLight: Story = {
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      colorScheme: 'light',
      backgroundColor: '#fafafa',
    }),
  },
};

export const FullCustom: Story = {
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      colorScheme: 'dark',
      accentColor: '#e91e63',
      accentHoverColor: '#c2185b',
      backgroundColor: '#1a1a2e',
      foregroundColor: '#e0e0e0',
      oddRowBackgroundColor: '#16213e',
      borderColor: '#0f3460',
    }),
  },
};
