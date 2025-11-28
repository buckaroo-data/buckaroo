import type { Meta, StoryObj } from "@storybook/react";
import { useMemo, useState } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { ShadowDomWrapper } from "./StoryUtils";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";

type DFRow = Record<string, any>;

const idxCol: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "obj" },
};

const objCol = (name: string): NormalColumnConfig => ({
  col_name: name,
  header_name: name,
  displayer_args: { displayer: "obj" },
});

const makeMainData = (): DFRow[] => [
  { index: 0, a: 1, b: "x" },
  { index: 1, a: 2, b: "y" },
  { index: 2, a: 3, b: "z" },
  { index: 3, a: 4, b: "w" },
  { index: 4, a: 5, b: "v" },
];

const pinnedConfig: DFViewerConfig = {
  column_config: [objCol("a"), objCol("b")],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "null_count", displayer_args: { displayer: "obj" } },
    { primary_key_val: "empty_count", displayer_args: { displayer: "obj" } },
  ],
};

// Summary stats rows for pinned extraction: objects with index = metric name
const makeSummary = (variant: "init" | "updated"): DFRow[] => {
  if (variant === "init") {
    return [
      { index: "null_count", a: 0, b: 1 },
      { index: "empty_count", a: 0, b: 2 },
    ];
  }
  return [
    { index: "null_count", a: 1, b: 0 },
    { index: "empty_count", a: 3, b: 1 },
  ];
};

const PinnedRowsDynamicInner = () => {
  const [summary, setSummary] = useState<DFRow[]>(makeSummary("init"));
  const data_wrapper = useMemo(
    () => ({
      data_type: "Raw" as const,
      data: makeMainData(),
      length: 5,
    }),
    [],
  );
  return (
    <ShadowDomWrapper>
      <div style={{ height: 420, width: 640 }}>
        <div style={{ marginBottom: 8 }}>
          <button onClick={() => setSummary((s) => (s[0]?.a === 0 ? makeSummary("updated") : makeSummary("init")))}>
            Toggle pinned rows
          </button>
        </div>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={pinnedConfig}
          summary_stats_data={summary}
          activeCol={["a", "a"]}
          setActiveCol={() => {}}
          outside_df_params={{}}
        />
      </div>
    </ShadowDomWrapper>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/PinnedRowsDynamic",
  component: PinnedRowsDynamicInner,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PinnedRowsDynamicInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {},
};


