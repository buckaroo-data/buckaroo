/**
 * Story that renders a full BuckarooInfiniteWidget with mock data,
 * exercising the real KeyAwareSmartRowCache + getDs() path.
 *
 * Used by Playwright tests to verify:
 *   1. Toggling to "summary" view shows pinned summary stats rows
 *   2. Searching via the status bar filters the table data
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

// ---------- mock data ----------

const NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"];
const TOTAL_ROWS = 5;

const allData: DFData = NAMES.map((name, i) => ({
  index: i,
  name,
  age: 25 + i * 3,
  score: 80 + i * 3.5,
}));

// Summary stats rows keyed by index (stat name)
const summaryStatsData: DFData = [
  { index: "dtype", name: "object", age: "int64", score: "float64" },
  { index: "count", name: 5, age: 5, score: 5 },
  { index: "unique", name: 5, age: 5, score: 5 },
  { index: "mean", name: "N/A", age: 34, score: 90.5 },
  { index: "min", name: "Alice", age: 25, score: 80 },
  { index: "max", name: "Eve", age: 37, score: 94 },
];

const SUMMARY_PINNED: PinnedRowConfig[] = summaryStatsData.map((row) => ({
  primary_key_val: row.index as string,
  displayer_args: { displayer: "obj" as const },
}));

const colConfig: DFViewerConfig = {
  column_config: [
    { col_name: "name", header_name: "name", displayer_args: { displayer: "obj" } },
    { col_name: "age", header_name: "age", displayer_args: { displayer: "integer", min_digits: 1, max_digits: 5 } },
    { col_name: "score", header_name: "score", displayer_args: { displayer: "float", min_fraction_digits: 1, max_fraction_digits: 2 } },
  ],
  pinned_rows: [],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "string" } }],
};

const summaryColConfig: DFViewerConfig = {
  ...colConfig,
  pinned_rows: SUMMARY_PINNED,
};

const df_display_args: Record<string, IDisplayArgs> = {
  main: {
    data_key: "main",
    df_viewer_config: colConfig,
    summary_stats_key: "all_stats",
  },
  summary: {
    data_key: "main",
    df_viewer_config: summaryColConfig,
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

const commandConfig: CommandConfigT = { commands: [] };

// ---------- component ----------

const BuckarooWidgetTestComponent: React.FC = () => {
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
      // Parse sourceName to check for search filter
      let filtered = allData;
      try {
        const params = JSON.parse(pa.sourceName || "[]");
        // outsideDFParams is [operations, post_processing, quick_command_args]
        // quick_command_args is at index 2 (after the fix) or may contain search
        const qca = params[2] || params[1]; // handle both old and new outsideDFParams shapes
        if (qca && typeof qca === "object" && qca.search && qca.search[0]) {
          const searchTerm = String(qca.search[0]).toLowerCase();
          filtered = allData.filter((row) =>
            String(row.name).toLowerCase().includes(searchTerm)
          );
        }
      } catch {
        // If sourceName isn't JSON or doesn't have search, use all data
      }

      const dataEnd = Math.min(pa.end, filtered.length);
      if (dataEnd <= pa.start) {
        // Send empty response with correct length
        const resp: PayloadResponse = {
          key: pa,
          data: [],
          length: filtered.length,
        };
        setTimeout(() => cache.addPayloadResponse(resp), 10);
        return;
      }
      const resp: PayloadResponse = {
        key: pa,
        data: filtered.slice(pa.start, dataEnd),
        length: filtered.length,
      };
      setTimeout(() => cache.addPayloadResponse(resp), 10);
    });
    return cache;
  }, []);

  const df_data_dict = useMemo(
    () => ({
      main: [] as DFData,
      all_stats: summaryStatsData,
      empty: [] as DFData,
    }),
    []
  );

  return (
    <div style={{ height: 600, width: 900 }}>
      <BuckarooInfiniteWidget
        df_meta={dfMeta}
        df_data_dict={df_data_dict}
        df_display_args={df_display_args}
        operations={operations}
        on_operations={setOperations}
        operation_results={{}}
        command_config={commandConfig}
        buckaroo_state={buckarooState}
        on_buckaroo_state={setBuckarooState}
        buckaroo_options={buckarooOptions}
        src={src}
      />
    </div>
  );
};

// ---------- storybook ----------

const meta = {
  title: "Buckaroo/BuckarooWidgetTest",
  component: BuckarooWidgetTestComponent,
  parameters: { layout: "centered" },
} satisfies Meta<typeof BuckarooWidgetTestComponent>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
