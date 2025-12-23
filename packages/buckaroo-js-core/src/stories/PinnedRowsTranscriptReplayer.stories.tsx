import type { Meta, StoryObj } from "@storybook/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { ShadowDomWrapper } from "./StoryUtils";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { createDatasourceWrapper, createRawDataWrapper } from "../components/DFViewerParts/DFViewerDataHelper";

type TranscriptEvent =
  | { ts: number; event: "pinned_rows_config"; pinned_keys: string[]; cfg: any }
  | { ts: number; event: "all_stats_update"; len: number; sample: any; all_stats: any[] }
  | { ts: number; event: "custom_msg"; msg: any; buffers_len: number }
  // DFViewerInfinite diagnostics
  | { ts: number; event: "dfi_cols_fields"; fields: string[] }
  | { ts: number; event: "dfi_pinned_extracted"; pinned_keys: string[]; summary_len: number; top_len: number }
  | { ts: number; event: "dfi_pinned_sample"; sample: any }
  | { ts: number; event: "dfi_pinned_apply"; len: number; applied_first: any }
  | { ts: number; event: "dfi_grid_ready"; pinned_count: number | null; pinned_first: any }
  | { ts: number; event: "dfi_first_data_rendered"; pinned_count: number | null; pinned_first: any }
  // Datasource + parsed rows
  | { ts: number; event: "ds_request"; args: any }
  | { ts: number; event: "ds_success"; args: any; rows_len: number; total_len: number }
  | { ts: number; event: "infinite_resp_parsed"; key: any; rows_len: number; total_len: number; rows?: any[] }
  | { ts: number; event: "user_operation"; operations: any[] };

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

const baseConfig: DFViewerConfig = {
  column_config: [objCol("a"), objCol("b")],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "null_count", displayer_args: { displayer: "obj" } },
    { primary_key_val: "empty_count", displayer_args: { displayer: "obj" } },
  ],
};

// Hardcoded transcript with 1-second gaps between user actions
// This transcript is recorded using: pw-tests/record-one-second-gap-transcript.spec.ts
// To update: 
//   1. Start JupyterLab: python3 -m jupyter lab --no-browser --port=8889 --ServerApp.token=test-token-12345
//   2. Run: cd packages/buckaroo-js-core && npx playwright test pw-tests/record-one-second-gap-transcript.spec.ts --config playwright.config.integration.ts
//   3. Copy the JSON from test output and paste here
const ONE_SECOND_GAP_TRANSCRIPT: TranscriptEvent[] = [
  // Sample transcript structure - replace with actual recorded transcript
  // Events are spaced with ~1000ms gaps between user actions (scrolling)
  {
    ts: 1000,
    event: "dfi_cols_fields",
    fields: ["index", "int_col", "str_col", "float_col"],
  },
  {
    ts: 1200,
    event: "all_stats_update",
    len: 2,
    sample: { index: "null_count", int_col: 0, str_col: 0, float_col: 0 },
    all_stats: [
      { index: "null_count", int_col: 0, str_col: 0, float_col: 0 },
      { index: "empty_count", int_col: 0, str_col: 0, float_col: 0 },
    ],
  },
  {
    ts: 1400,
    event: "pinned_rows_config",
    pinned_keys: ["null_count", "empty_count"],
    cfg: {
      pinned_rows: [
        { primary_key_val: "null_count", displayer_args: { displayer: "obj" } },
        { primary_key_val: "empty_count", displayer_args: { displayer: "obj" } },
      ],
    },
  },
  {
    ts: 2000, // 1 second after first action
    event: "custom_msg",
    msg: { type: "infinite_resp", key: { start: 0, end: 100 } },
    buffers_len: 1,
  },
  {
    ts: 2200,
    event: "infinite_resp_parsed",
    key: { start: 0, end: 100 },
    rows_len: 100,
    total_len: 5000,
    rows: Array.from({ length: 100 }, (_, i) => ({
      index: i,
      int_col: i + 10,
      str_col: `row_${i}`,
      float_col: i * 1.5,
    })),
  },
  {
    ts: 3000, // 1 second after previous user action
    event: "custom_msg",
    msg: { type: "infinite_resp", key: { start: 100, end: 200 } },
    buffers_len: 1,
  },
  {
    ts: 3200,
    event: "infinite_resp_parsed",
    key: { start: 100, end: 200 },
    rows_len: 100,
    total_len: 5000,
    rows: Array.from({ length: 100 }, (_, i) => ({
      index: i + 100,
      int_col: i + 110,
      str_col: `row_${i + 100}`,
      float_col: (i + 100) * 1.5,
    })),
  },
  {
    ts: 4000, // 1 second after previous user action
    event: "custom_msg",
    msg: { type: "infinite_resp", key: { start: 200, end: 300 } },
    buffers_len: 1,
  },
  {
    ts: 4200,
    event: "infinite_resp_parsed",
    key: { start: 200, end: 300 },
    rows_len: 100,
    total_len: 5000,
    rows: Array.from({ length: 100 }, (_, i) => ({
      index: i + 200,
      int_col: i + 210,
      str_col: `row_${i + 200}`,
      float_col: (i + 200) * 1.5,
    })),
  },
];

//window._buckarooTranscript =
const PinnedRowsTranscriptReplayerInner = () => {
  const [summary, setSummary] = useState<any[]>([]);
  const [cfg, setCfg] = useState<DFViewerConfig>(baseConfig);
  const [rawRows, setRawRows] = useState<any[]>([]);
  const eventsRef = useRef<TranscriptEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const data_wrapper = useMemo(() => {
    // Prefer exact rows from transcript if available; otherwise start empty DataSource(0 rows)
    if (rawRows && rawRows.length > 0) {
      return createRawDataWrapper(rawRows);
    }
    return createDatasourceWrapper([], 0);
  }, [rawRows]);

  useEffect(() => {
    // Check if we should use the hardcoded 1-second gap transcript
    // Use a small delay to ensure decorator has set the flag
    const checkTranscript = () => {
      // @ts-ignore
      const useHardcoded = (window as any)._buckarooTranscriptOneSecondGap === true;
      
      if (useHardcoded && ONE_SECOND_GAP_TRANSCRIPT.length > 0) {
        console.log(`[Replay] Loading hardcoded transcript with ${ONE_SECOND_GAP_TRANSCRIPT.length} events`);
        eventsRef.current = ONE_SECOND_GAP_TRANSCRIPT.slice();
      } else {
        // pull transcript from the window if present
        // @ts-ignore
        const t: TranscriptEvent[] = (window as any)._buckarooTranscript || [];
        console.log(`[Replay] Loading window transcript with ${t.length} events`);
        eventsRef.current = Array.isArray(t) ? t.slice() : [];
      }
    };
    
    // Check immediately and also after a tiny delay to handle race conditions
    checkTranscript();
    const timeoutId = setTimeout(checkTranscript, 10);
    return () => clearTimeout(timeoutId);
  }, []);

  const start = () => {
    if (isRunning) return;
    setIsRunning(true);
    const evs = eventsRef.current.slice().sort((a, b) => a.ts - b.ts);
    
    // Use relative timing between consecutive events to preserve gaps
    // This ensures 1-second gaps in the transcript are replayed as 1-second gaps
    let cumulativeDelay = 0;
    evs.forEach((ev, index) => {
      if (index === 0) {
        // First event happens immediately
        cumulativeDelay = 0;
      } else {
        // Calculate delay relative to previous event
        const prevEv = evs[index - 1];
        const timeSincePrev = ev.ts - prevEv.ts;
        // Preserve the actual gap, but ensure minimum 10ms for identical timestamps
        cumulativeDelay += Math.max(timeSincePrev, 10);
      }
      
      // Capture the delay for this specific event in the closure
      const eventDelay = cumulativeDelay;
      
      setTimeout(() => {
        const fireTime = Date.now();
        console.log(`[Replay] Event ${index + 1}/${evs.length} fired at ${fireTime}, delay was ${eventDelay}ms, event: ${ev.event}`);
        
        if (ev.event === "pinned_rows_config") {
          const keys = ev.pinned_keys || [];
          setCfg((old) => ({
            ...old,
            pinned_rows: keys.map((k) => ({ primary_key_val: k, displayer_args: { displayer: "obj" } })),
          }));
        } else if (ev.event === "dfi_cols_fields") {
          const fields = ev.fields || [];
          const dataFields = fields.filter((f) => f && f !== "index");
          setCfg((old) => ({
            ...old,
            column_config: dataFields.map((f) => objCol(f)),
            left_col_configs: [idxCol],
          }));
        } else if (ev.event === "all_stats_update") {
          // Deep-clone to break identity and make BigInt JSON-safe
          const safe = (function toJsonSafe(val: any): any {
            if (typeof val === "bigint") return val.toString();
            if (Array.isArray(val)) return val.map((v) => toJsonSafe(v));
            if (val && typeof val === "object") {
              const out: Record<string, any> = {};
              for (const k in val) {
                try {
                  out[k] = toJsonSafe(val[k]);
                } catch {
                  out[k] = null;
                }
              }
              return out;
            }
            return val;
          })(ev.all_stats || []);
          setSummary(safe);
        } else if (ev.event === "infinite_resp_parsed" && ev.rows && Array.isArray(ev.rows)) {
          // Use the exact rows parsed from the transcript
          const rows = ev.rows as any[];
          setRawRows(Array.isArray(rows) ? rows : []);
        } else if (ev.event === "ds_success") {
          // If no rows captured yet but datasource succeeded, at least switch to an empty Raw set to clear "None"
          if (rawRows.length === 0) setRawRows([]);
        }
      }, eventDelay);
    });
  };

  return (
    <ShadowDomWrapper>
      <div style={{ width: 760 }}>
        <p style={{ marginBottom: 8 }}>
          Replays a captured transcript (window._buckarooTranscript) of model updates and custom messages,
          applying pinned row config, summary updates (all_stats), and simulating infinite responses by
          switching to 5 visible rows. Click Start after running the Jupyter widget with transcript logging
          enabled to reproduce the behavior here.
        </p>
        <div style={{ marginBottom: 8 }}>
          <button onClick={start} disabled={isRunning}>
            Start Replay
          </button>
          <span style={{ marginLeft: 12 }}>events: {eventsRef.current.length}</span>
        </div>
        <div style={{ height: 420 }}>
          <DFViewerInfinite
            data_wrapper={data_wrapper}
            df_viewer_config={cfg}
            summary_stats_data={summary}
            activeCol={["a", "a"]}
            setActiveCol={() => {}}
            outside_df_params={{}}
          />
        </div>
      </div>
    </ShadowDomWrapper>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/PinnedRowsTranscriptReplayer",
  component: PinnedRowsTranscriptReplayerInner,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof PinnedRowsTranscriptReplayerInner>;

export default meta;
type Story = StoryObj<typeof meta>;
export const Primary: Story = { args: {} };

export const OneSecondGap: Story = {
  args: {},
  decorators: [
    (Story) => {
      // Set flag synchronously before component renders
      // @ts-ignore
      if (typeof window !== 'undefined') {
        // @ts-ignore
        window._buckarooTranscriptOneSecondGap = true;
      }
      return <Story />;
    },
  ],
};


