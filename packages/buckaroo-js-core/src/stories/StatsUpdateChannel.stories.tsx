/**
 * The stats wire from the client side (rows-first c2), with no server.
 *
 * A real WebSocketModel renders through BuckarooView in buckaroo mode, but its
 * socket is FakeStatsServer, which answers the way the Python server does:
 *
 *   - infinite_request → infinite_resp (JSON frame, then a binary frame) after
 *     rowDelayMs, filtered by the server's current search.
 *   - buckaroo_state_change → initial_state after stateDelayMs, carrying a new
 *     stats gen whose df_meta.stats is pending and whose all_stats holds only
 *     the schema-tier dtype row.
 *
 * stats_update frames go out only when a "deliver" button is clicked, one pair
 * of buttons per gen the server has issued, so the order of the stats against
 * the other frames is up to the person (or test) clicking. Each gen's `mean`
 * row comes in two column chunks, the way a column-chunked tier sends it: `age`
 * (not final), then `score` (final). Each chunk pads the column it does not
 * carry with null, as the wide pivot does, so the `score` chunk also checks
 * that a null leaves an already-merged value alone. Used by
 * stats-update-channel.spec.ts.
 */
import type { Meta, StoryObj } from "@storybook/react";
import React, { useEffect, useMemo, useState } from "react";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import { PayloadArgs } from "../components/DFViewerParts/SmartRowCache";
import { BuckarooOptions, BuckarooState, DFMeta, DFMetaStats } from "../components/WidgetTypes";
import { BuckarooView } from "../server/BuckarooView";
import { WebSocketModel } from "../server/WebSocketModel";

const NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"];

const allRows: DFData = NAMES.map((name, i) => ({
  index: i,
  name,
  age: 25 + i * 3,
  score: 80 + i * 3.5,
}));

const mean = (rows: DFData, col: "age" | "score") =>
  rows.length === 0 ? null : rows.reduce((acc, r) => acc + (r[col] as number), 0) / rows.length;

const schemaStats = (): DFData => [{ index: "dtype", name: "object", age: "int64", score: "float64" }];

const floatArgs = { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 2 } as const;

const viewerConfig: DFViewerConfig = {
  column_config: [
    { col_name: "name", header_name: "name", displayer_args: { displayer: "obj" } },
    { col_name: "age", header_name: "age", displayer_args: { displayer: "integer", min_digits: 1, max_digits: 5 } },
    { col_name: "score", header_name: "score", displayer_args: floatArgs },
  ],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } }],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "mean", displayer_args: floatArgs },
  ],
};

const dfDisplayArgs: Record<string, IDisplayArgs> = {
  main: { data_key: "main", df_viewer_config: viewerConfig, summary_stats_key: "all_stats" },
};

const buckarooOptions: BuckarooOptions = {
  sampled: [],
  cleaning_method: [],
  post_processing: [],
  df_display: ["main"],
  show_commands: [],
};

const initialBuckarooState: BuckarooState = {
  sampled: false,
  cleaning_method: false,
  quick_command_args: {},
  post_processing: false,
  df_display: "main",
  show_commands: false,
};

const metaFor = (rows: DFData, gen: number): DFMeta => ({
  total_rows: allRows.length,
  columns: 3,
  filtered_rows: rows.length,
  rows_shown: rows.length,
  stats: { status: "pending", tier: "schema", gen },
});

type StatsChunk = "age" | "score";

interface FakeServerOptions {
  rowDelayMs: number;
  stateDelayMs: number;
  // Called whenever the server issues a new gen, so the controls can re-render.
  onGen: (gen: number) => void;
}

/** The socket WebSocketModel is built on: it takes the client's frames through
 *  send() and answers through the onmessage handler the model installs. */
class FakeStatsServer {
  readyState = 1; // WebSocket.OPEN
  onmessage: ((e: MessageEvent) => void) | null = null;
  gen = 1;
  private rowsByGen = new Map<number, DFData>([[1, allRows]]);

  constructor(private opts: FakeServerOptions) {}

  get rows(): DFData {
    return this.rowsByGen.get(this.gen) ?? [];
  }

  send(data: string): void {
    const msg = JSON.parse(data);
    if (msg.type === "infinite_request") {
      this.answerRows(msg.payload_args as PayloadArgs, this.rows);
    } else if (msg.type === "buckaroo_state_change") {
      this.answerStateChange(msg.new_state as BuckarooState);
    }
  }

  /** Sends one column chunk of `gen`'s stats as a stats_update, the way the
   *  server answers a stats_request. The `score` chunk is the final one. */
  deliverStats(gen: number, column: StatsChunk): void {
    const rows = this.rowsByGen.get(gen) ?? [];
    const meanRow = {
      index: "mean",
      name: null,
      age: column === "age" ? mean(rows, "age") : null,
      score: column === "score" ? mean(rows, "score") : null,
    };
    const final = column === "score";
    this.push({
      type: "stats_update",
      stats_gen: gen,
      scope: "raw",
      tier: "full",
      final,
      payload: { format: "json", data: [meanRow] },
      elapsed_ms: 1,
    });
  }

  private answerRows(pa: PayloadArgs, rows: DFData): void {
    setTimeout(() => {
      this.push({
        type: "infinite_resp",
        key: pa,
        length: rows.length,
        payload: { format: "json", data: rows.slice(pa.start, Math.min(pa.end, rows.length)) },
      });
      // The model pairs every infinite_resp with the binary frame after it.
      this.onmessage?.({ data: new ArrayBuffer(0) } as MessageEvent);
    }, this.opts.rowDelayMs);
  }

  private answerStateChange(state: BuckarooState): void {
    const term = String(state.quick_command_args?.search?.[0] ?? "").toLowerCase();
    const rows = allRows.filter((r) => String(r.name).toLowerCase().includes(term));
    this.gen += 1;
    const gen = this.gen;
    this.rowsByGen.set(gen, rows);
    this.opts.onGen(gen);
    setTimeout(() => {
      this.push({
        type: "initial_state",
        df_meta: metaFor(rows, gen),
        df_data_dict: { main: [], all_stats: schemaStats(), empty: [] },
        buckaroo_state: state,
      });
    }, this.opts.stateDelayMs);
  }

  private push(msg: object): void {
    this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
  }
}

const describeStats = (stats?: DFMetaStats) =>
  stats ? `${stats.status} ${stats.tier ?? "-"} gen ${stats.gen ?? "-"}` : "none";

interface StatsUpdateChannelProps {
  // How long the server takes to answer a row request.
  rowDelayMs: number;
  // How long the server takes to answer a state change (a search).
  stateDelayMs: number;
}

const StatsUpdateChannel: React.FC<StatsUpdateChannelProps> = ({ rowDelayMs, stateDelayMs }) => {
  const [serverGen, setServerGen] = useState(1);
  const [modelStats, setModelStats] = useState<DFMetaStats | undefined>(undefined);
  const [statRows, setStatRows] = useState<string[]>([]);
  const [settled, setSettled] = useState(0);

  const { server, model, initialState } = useMemo(() => {
    const server = new FakeStatsServer({ rowDelayMs, stateDelayMs, onGen: setServerGen });
    const initialState = {
      df_meta: metaFor(allRows, 1),
      df_data_dict: { main: [], all_stats: schemaStats(), empty: [] },
      df_display_args: dfDisplayArgs,
      buckaroo_state: initialBuckarooState,
      buckaroo_options: buckarooOptions,
    };
    const model = new WebSocketModel(server as unknown as WebSocket, initialState);
    return { server, model, initialState };
  }, [rowDelayMs, stateDelayMs]);

  // Mirror what the model holds, not what the grid renders, so a dropped
  // update can be told from one that has not rendered yet.
  useEffect(() => {
    const onMeta = (meta: DFMeta) => setModelStats(meta?.stats);
    const onDict = (dict: Record<string, unknown>) => {
      const allStats = dict?.all_stats;
      setStatRows(Array.isArray(allStats) ? allStats.map((r) => String(r.index)) : []);
    };
    onMeta(model.get("df_meta"));
    onDict(model.get("df_data_dict"));
    model.on("change:df_meta", onMeta);
    model.on("change:df_data_dict", onDict);
    return () => {
      model.off("change:df_meta", onMeta);
      model.off("change:df_data_dict", onDict);
    };
  }, [model]);

  // A json payload merges within microtasks, so once a macrotask has run after
  // a delivery the model holds whatever the delivery did; "settled" counts
  // those deliveries.
  const deliver = (gen: number, column: StatsChunk) => {
    server.deliverStats(gen, column);
    setTimeout(() => setSettled((n) => n + 1), 0);
  };

  const gens = Array.from({ length: serverGen }, (_, i) => i + 1);
  return (
    <div style={{ width: 760 }}>
      <div style={{ padding: "8px 12px", marginBottom: 8, fontFamily: "monospace", fontSize: 12 }}>
        <div>
          server gen: <span data-testid="server-gen">{serverGen}</span>
          {" · "}model df_meta.stats: <span data-testid="model-stats">{describeStats(modelStats)}</span>
          {" · "}model all_stats rows: <span data-testid="model-stat-rows">{statRows.join(",")}</span>
          {" · "}deliveries settled: <span data-testid="settled">{settled}</span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
          {gens.map((gen) => (
            <React.Fragment key={gen}>
              <button data-testid={`deliver-age-gen-${gen}`} onClick={() => deliver(gen, "age")}>
                gen {gen}: age stats
              </button>
              <button data-testid={`deliver-score-gen-${gen}`} onClick={() => deliver(gen, "score")}>
                gen {gen}: score stats (final)
              </button>
            </React.Fragment>
          ))}
        </div>
      </div>
      <div style={{ height: 360 }}>
        <BuckarooView model={model} initialState={initialState} mode="buckaroo" />
      </div>
    </div>
  );
};

const meta = {
  title: "Buckaroo/Server/StatsUpdateChannel",
  component: StatsUpdateChannel,
  parameters: { layout: "centered" },
  argTypes: {
    rowDelayMs: { control: { type: "range", min: 0, max: 3000, step: 50 } },
    stateDelayMs: { control: { type: "range", min: 0, max: 3000, step: 50 } },
  },
} satisfies Meta<typeof StatsUpdateChannel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Manual: Story = {
  args: { rowDelayMs: 10, stateDelayMs: 10 },
};
