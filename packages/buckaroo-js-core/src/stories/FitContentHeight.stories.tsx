/**
 * Story for the `layoutType: "fitContent"` height mode.
 *
 * The widget (5 rows) is mounted in a deliberately over-tall 600px container.
 * In "fitContent" mode the widget sizes its own outer box to its content, so it
 * collapses well below 600px with no gap — the host did not have to match the
 * viewport height. The red border marks the container; with fitContent the
 * widget should end flush with the table, not stretch to the border.
 */
import type { Meta, StoryObj } from "@storybook/react";
import React, { useMemo, useState } from "react";
import { BuckarooInfiniteWidget } from "../components/BuckarooWidgetInfinite";
import { DFData, DFViewerConfig, PinnedRowConfig } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import {
  KeyAwareSmartRowCache,
  PayloadArgs,
  PayloadResponse,
} from "../components/DFViewerParts/SmartRowCache";
import { BuckarooOptions, BuckarooState, DFMeta } from "../components/WidgetTypes";
import { CommandConfigT } from "../components/CommandUtils";
import { Operation } from "../components/OperationUtils";
import { baseOperationResults } from "../components/DependentTabs";

const NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"];
const TOTAL_ROWS = 5;

const allData: DFData = NAMES.map((name, i) => ({
  index: i,
  name,
  age: 25 + i * 3,
  score: 80 + i * 3.5,
}));

const summaryStatsData: DFData = [
  { index: "dtype", name: "object", age: "int64", score: "float64" },
  { index: "count", name: 5, age: 5, score: 5 },
];

const SUMMARY_PINNED: PinnedRowConfig[] = summaryStatsData.map((row) => ({
  primary_key_val: row.index as string,
  displayer_args: { displayer: "obj" as const },
}));

// The fitContent layout lives on component_config, exactly where the server /
// Python side would set it.
const colConfig: DFViewerConfig = {
  column_config: [
    { col_name: "name", header_name: "name", displayer_args: { displayer: "obj" } },
    { col_name: "age", header_name: "age", displayer_args: { displayer: "integer", min_digits: 1, max_digits: 5 } },
    { col_name: "score", header_name: "score", displayer_args: { displayer: "float", min_fraction_digits: 1, max_fraction_digits: 2 } },
  ],
  pinned_rows: [],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "string" } }],
  component_config: { layoutType: "fitContent" },
};

const df_display_args: Record<string, IDisplayArgs> = {
  main: { data_key: "main", df_viewer_config: colConfig, summary_stats_key: "all_stats" },
  summary: {
    data_key: "main",
    df_viewer_config: { ...colConfig, pinned_rows: SUMMARY_PINNED },
    summary_stats_key: "all_stats",
  },
};

const dfMeta: DFMeta = {
  total_rows: TOTAL_ROWS,
  columns: 3,
  filtered_rows: TOTAL_ROWS,
  rows_shown: TOTAL_ROWS,
};

const buckarooOptions: BuckarooOptions = {
  sampled: [],
  cleaning_method: [],
  post_processing: [],
  df_display: ["main", "summary"],
  show_commands: [],
};

const commandConfig: CommandConfigT = { argspecs: {}, defaultArgs: {} };

const FitContentComponent: React.FC = () => {
  const [buckarooState, setBuckarooState] = useState<BuckarooState>({
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
  });
  const [operations, setOperations] = useState<Operation[]>([]);

  const src = useMemo(() => {
    const cache = new KeyAwareSmartRowCache((pa: PayloadArgs) => {
      const dataEnd = Math.min(pa.end, allData.length);
      const resp: PayloadResponse = {
        key: pa,
        data: dataEnd <= pa.start ? [] : allData.slice(pa.start, dataEnd),
        length: allData.length,
      };
      setTimeout(() => cache.addPayloadResponse(resp), 10);
    });
    return cache;
  }, []);

  const df_data_dict = useMemo(
    () => ({ main: [] as DFData, all_stats: summaryStatsData, empty: [] as DFData }),
    []
  );

  return (
    <div
      data-testid="height-container"
      style={{ height: 600, width: 900, background: "#181D1F", border: "2px solid red" }}
    >
      <BuckarooInfiniteWidget
        df_meta={dfMeta}
        df_data_dict={df_data_dict}
        df_display_args={df_display_args}
        operations={operations}
        on_operations={setOperations}
        operation_results={baseOperationResults}
        command_config={commandConfig}
        buckaroo_state={buckarooState}
        on_buckaroo_state={setBuckarooState}
        buckaroo_options={buckarooOptions}
        src={src}
      />
    </div>
  );
};

const meta = {
  title: "Buckaroo/FitContentHeight",
  component: FitContentComponent,
  parameters: { layout: "padded" },
} satisfies Meta<typeof FitContentComponent>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
