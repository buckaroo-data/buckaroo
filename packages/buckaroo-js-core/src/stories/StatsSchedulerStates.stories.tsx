/**
 * Story for the client states of the stats wire (rows-first c4).
 *
 * df_meta.stats.status says where the summary stats stand, and the status bar
 * shows it in a column of its own:
 *
 *   - "pending"       "Computing summary stats", pinned keys show placeholders
 *   - "not_computed"  a "Compute summary stats" button, pinned keys omitted
 *   - "error"         "Stats error: <reason>", pinned keys omitted
 *   - "complete"      "Summary stats ready", the values in place
 *
 * The buttons switch the status. The button in the status bar sends
 * `stats_request {force: true}` through a fake model, which logs what it was
 * asked to send. Used by stats-scheduler-states.spec.ts.
 */
import type { Meta, StoryObj } from "@storybook/react";
import React, { useMemo, useState } from "react";
import "../style/dcf-npm.css";
import { BuckarooInfiniteWidget } from "../components/BuckarooWidgetInfinite";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import { KeyAwareSmartRowCache, PayloadResponse } from "../components/DFViewerParts/SmartRowCache";
import { BuckarooOptions, BuckarooState, DFMeta, StatsStatus } from "../components/WidgetTypes";
import { CommandConfigT } from "../components/CommandUtils";
import { Operation } from "../components/OperationUtils";
import { baseOperationResults } from "../components/DependentTabs";
import { requestStats } from "../server/StateOrchestrator";

const STATUSES: StatsStatus[] = ["pending", "not_computed", "error", "complete"];
const GEN = 7;

const mainData: DFData = [
  { index: 0, a: 1, b: "x" },
  { index: 1, a: 2, b: "y" },
  { index: 2, a: 3, b: "z" },
];

const completeStats: DFData = [
  { index: "dtype", a: "int64", b: "object" },
  { index: "mean", a: 2, b: "N/A" },
];

const viewerConfig: DFViewerConfig = {
  column_config: [
    { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
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

const buckarooOptions: BuckarooOptions = {
  sampled: [],
  cleaning_method: [],
  post_processing: [],
  df_display: ["main"],
  show_commands: [],
};
const commandConfig: CommandConfigT = { argspecs: {}, defaultArgs: {} };

const StatsSchedulerStatesInner: React.FC = () => {
  const [status, setStatus] = useState<StatsStatus>("pending");
  const [sent, setSent] = useState<unknown[]>([]);
  const [buckarooState, setBuckarooState] = useState<BuckarooState>({
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
  });
  const [operations, setOperations] = useState<Operation[]>([]);

  const df_meta = useMemo(
    () =>
      ({
        total_rows: mainData.length,
        columns: 2,
        filtered_rows: mainData.length,
        rows_shown: mainData.length,
        stats: {
          status,
          tier: status === "complete" ? "full" : "schema",
          gen: GEN,
          ...(status === "error" ? { reason: "stats_failed" } : {}),
        },
      }) as DFMeta,
    [status],
  );

  // The model the control sends through: it answers get("df_meta") from the
  // story's state and logs what it is asked to send.
  const model = useMemo(
    () => ({
      get: (key: string) => (key === "df_meta" ? df_meta : undefined),
      send: (msg: unknown) => setSent((log) => [...log, msg]),
    }),
    [df_meta],
  );

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

  const df_data_dict = useMemo(
    () => ({
      main: [] as DFData,
      all_stats: status === "complete" ? completeStats : ([] as DFData),
      empty: [] as DFData,
    }),
    [status],
  );

  return (
    <div style={{ width: 900 }}>
      <div style={{ padding: "8px 12px", marginBottom: 8 }}>
        {STATUSES.map((s) => (
          <button key={s} data-testid={`status-${s}`} onClick={() => setStatus(s)} style={{ marginRight: 8 }}>
            {s}
          </button>
        ))}
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>df_meta.stats.status = {status}</span>
      </div>
      <div style={{ height: 400 }} data-testid="widget-host">
        <BuckarooInfiniteWidget
          df_meta={df_meta}
          df_data_dict={df_data_dict}
          df_display_args={displayArgs}
          operations={operations}
          on_operations={setOperations}
          operation_results={baseOperationResults}
          command_config={commandConfig}
          buckaroo_state={buckarooState}
          on_buckaroo_state={setBuckarooState}
          buckaroo_options={buckarooOptions}
          src={src}
          on_compute_stats={() => requestStats(model, { force: true })}
        />
      </div>
      <pre data-testid="sent-log" style={{ fontSize: 12 }}>
        {JSON.stringify(sent)}
      </pre>
    </div>
  );
};

const meta = {
  title: "Buckaroo/StatsSchedulerStates",
  component: StatsSchedulerStatesInner,
  parameters: { layout: "centered" },
} satisfies Meta<typeof StatsSchedulerStatesInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
