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
 * The buttons switch the status. The "partial" button is "pending" with the
 * stats of one column in, as a partial stats_update leaves them. The button in
 * the status bar sends `stats_request {force: true, incremental: true, tier}`
 * through a fake model, which logs what it was asked to send and answers
 * `visible_columns` with the columns the grid reports. Used by
 * stats-scheduler-states.spec.ts.
 *
 * The NotComputed story (rows-first c5) is a session the server's policy left
 * without stats: typed columns over schema-tier stats, a main and a summary
 * view, and the policy in df_meta.stats. The buttons switch the view and the
 * reason the stats were not computed; the controls send through `forceStats`.
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
import { forceStats } from "../server/StateOrchestrator";

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

// dtype comes with the schema; mean has arrived for column a only.
const partialStats: DFData = [
  { index: "dtype", a: "int64", b: "object" },
  { index: "mean", a: 2 },
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
  const [partial, setPartial] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);
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

  // The model the control sends through: it answers get("df_meta") and
  // get("visible_columns") from the story's state and logs what it is asked to
  // send.
  const model = useMemo(
    () => ({
      get: (key: string) => (key === "df_meta" ? df_meta : key === "visible_columns" ? visibleColumns : undefined),
      set: () => {},
      send: (msg: unknown) => setSent((log) => [...log, msg]),
    }),
    [df_meta, visibleColumns],
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
      all_stats: status === "complete" ? completeStats : partial ? partialStats : ([] as DFData),
      empty: [] as DFData,
    }),
    [status, partial],
  );

  return (
    <div style={{ width: 900 }}>
      <div style={{ padding: "8px 12px", marginBottom: 8 }}>
        {STATUSES.map((s) => (
          <button
            key={s}
            data-testid={`status-${s}`}
            onClick={() => {
              setStatus(s);
              setPartial(false);
            }}
            style={{ marginRight: 8 }}
          >
            {s}
          </button>
        ))}
        <button
          data-testid="status-partial"
          onClick={() => {
            setStatus("pending");
            setPartial(true);
          }}
          style={{ marginRight: 8 }}
        >
          partial
        </button>
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
          on_compute_stats={(opts) => forceStats(model, opts)}
          on_visible_columns={setVisibleColumns}
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


// ---- NotComputed: a session whose stats the server's policy did not compute ----

type Reason = "size" | "ceiling" | "cost";
const REASONS: Record<Reason, { reason: string; requestable: string[] }> = {
  size: { reason: "size", requestable: ["scalar", "full"] },
  ceiling: { reason: "ceiling", requestable: [] },
  cost: { reason: "cost", requestable: ["full"] },
};

const typedData: DFData = [
  { index: 0, a: 1, b: "x", c: 1.5 },
  { index: 1, a: 2, b: "y", c: 2.25 },
  { index: 2, a: 3, b: "z", c: 3 },
];

// What the schema tier sends: dtype and identity keys, nothing computed.
const schemaStats: DFData = [
  { index: "dtype", a: "int64", b: "object", c: "float64" },
  { index: "length", a: 3, b: 3, c: 3 },
];

const typedColumns: DFViewerConfig["column_config"] = [
  { col_name: "a", header_name: "a", displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 } },
  { col_name: "b", header_name: "b", displayer_args: { displayer: "string", max_length: 35 } },
  { col_name: "c", header_name: "c", displayer_args: { displayer: "float", min_fraction_digits: 3, max_fraction_digits: 3 } },
];
const indexColumn: DFViewerConfig["left_col_configs"] = [
  { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
];
// dtype is in the schema stats; histogram is not, and no value is coming.
const typedPinned: DFViewerConfig["pinned_rows"] = [
  { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
  { primary_key_val: "histogram", displayer_args: { displayer: "histogram" } },
];

const notComputedDisplayArgs: Record<string, IDisplayArgs> = {
  main: {
    data_key: "main",
    df_viewer_config: { column_config: typedColumns, left_col_configs: indexColumn, pinned_rows: typedPinned },
    summary_stats_key: "all_stats",
  },
  summary: {
    data_key: "empty",
    df_viewer_config: {
      column_config: typedColumns,
      left_col_configs: indexColumn,
      pinned_rows: [{ primary_key_val: "dtype", displayer_args: { displayer: "obj" } }],
    },
    summary_stats_key: "all_stats",
  },
};

const notComputedOptions: BuckarooOptions = { ...buckarooOptions, df_display: ["main", "summary"] };

const NotComputedInner: React.FC = () => {
  const [reason, setReason] = useState<Reason>("size");
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
        total_rows: typedData.length,
        columns: 3,
        filtered_rows: typedData.length,
        rows_shown: typedData.length,
        stats: {
          status: "not_computed",
          tier: "schema",
          gen: GEN,
          reason: REASONS[reason].reason,
          tier_target: "schema",
          estimate: { rows: 12_400_000, cols: 3 },
          auto_request: false,
          requestable: REASONS[reason].requestable,
        },
      }) as DFMeta,
    [reason],
  );

  // The model the controls send through: it answers get("df_meta") from the
  // story's state and logs what it is asked to send.
  const model = useMemo(
    () => ({
      get: (key: string) => (key === "df_meta" ? df_meta : undefined),
      set: () => {},
      send: (msg: unknown) => setSent((log) => [...log, msg]),
    }),
    [df_meta],
  );

  const src = useMemo(() => {
    const cache = new KeyAwareSmartRowCache((pa) => {
      const resp: PayloadResponse = {
        key: pa,
        data: typedData.slice(pa.start, Math.min(pa.end, typedData.length)),
        length: typedData.length,
      };
      setTimeout(() => cache.addPayloadResponse(resp), 10);
    });
    return cache;
  }, []);

  const df_data_dict = useMemo(
    () => ({ main: [] as DFData, all_stats: schemaStats, empty: [] as DFData }),
    [],
  );

  const setView = (view: string) => setBuckarooState((state) => ({ ...state, df_display: view }));

  return (
    <div style={{ width: 900 }}>
      <div style={{ padding: "8px 12px", marginBottom: 8 }}>
        {["main", "summary"].map((view) => (
          <button key={view} data-testid={`view-${view}`} onClick={() => setView(view)} style={{ marginRight: 8 }}>
            {view}
          </button>
        ))}
        {(Object.keys(REASONS) as Reason[]).map((r) => (
          <button key={r} data-testid={`policy-${r}`} onClick={() => setReason(r)} style={{ marginRight: 8 }}>
            {r}
          </button>
        ))}
        <span style={{ fontFamily: "monospace", fontSize: 12 }}>reason = {reason}</span>
      </div>
      <div style={{ height: 400 }} data-testid="widget-host">
        <BuckarooInfiniteWidget
          df_meta={df_meta}
          df_data_dict={df_data_dict}
          df_display_args={notComputedDisplayArgs}
          operations={operations}
          on_operations={setOperations}
          operation_results={baseOperationResults}
          command_config={commandConfig}
          buckaroo_state={buckarooState}
          on_buckaroo_state={setBuckarooState}
          buckaroo_options={notComputedOptions}
          src={src}
          on_compute_stats={(opts) => forceStats(model, opts)}
        />
      </div>
      <pre data-testid="sent-log" style={{ fontSize: 12 }}>
        {JSON.stringify(sent)}
      </pre>
    </div>
  );
};

export const NotComputed: Story = {
  render: () => <NotComputedInner />,
};
