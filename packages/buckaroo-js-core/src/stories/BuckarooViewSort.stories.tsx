/*
  BuckarooView with a host-supplied sort (#984).

  A fake IModel stands in for the server: it answers each infinite_request
  from an in-memory frame, sorted by the request's sort / sort_direction the
  way the server does. The frame is laid out like tallyman's diff frame:
  `b` holds the before value and is hidden, `c` is the after value shown
  under the header "fare". The host asks for { column: "fare", direction:
  "desc" }, which has to resolve to `c`. Sorting on `b` instead would put
  Braund first.

  The story prints the first row request's sort and every onSortChange call
  for pw-tests/buckaroo-view-sort.spec.ts to read.
*/
import type { Meta, StoryObj } from "@storybook/react";
import React, { useMemo, useState } from "react";
import { BuckarooView } from "../server/BuckarooView";
import type { IModel } from "../server/IModel";
import type { HeaderSort } from "../components/DFViewerParts/gridUtils";
import type { DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import type { PayloadArgs } from "../components/DFViewerParts/SmartRowCache";

type Row = { index: number; a: string; b: number; c: number };

const ROWS: Row[] = [
  { index: 0, a: "Braund", b: 100, c: 7.5 },
  { index: 1, a: "Cumings", b: 1, c: 70 },
  { index: 2, a: "Heikkinen", b: 2, c: 8 },
  { index: 3, a: "Futrelle", b: 3, c: 55 },
  { index: 4, a: "Allen", b: 4, c: 9 },
];

const diffConfig: DFViewerConfig = {
  pinned_rows: [],
  left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } }],
  column_config: [
    { col_name: "a", header_name: "name", displayer_args: { displayer: "obj" } },
    { col_name: "b", header_name: "fare", displayer_args: { displayer: "obj" }, ag_grid_specs: { hide: true } },
    { col_name: "c", header_name: "fare", displayer_args: { displayer: "obj" } },
  ],
};

const initialState = {
  df_meta: { total_rows: ROWS.length, columns: 3, filtered_rows: ROWS.length, rows_shown: ROWS.length },
  df_data_dict: { all_stats: [] },
  df_display_args: {
    main: { data_key: "main", df_viewer_config: diffConfig, summary_stats_key: "all_stats" },
  },
};

const sortRows = (rows: Row[], sort?: string, direction?: string): Row[] => {
  if (!sort) return rows;
  const key = sort as keyof Row;
  const sign = direction === "desc" ? -1 : 1;
  return [...rows].sort((x, y) => (x[key] < y[key] ? -sign : x[key] > y[key] ? sign : 0));
};

const makeFakeModel = (onRequest: (pa: PayloadArgs) => void): IModel => {
  const handlers = new Map<string, Set<(...args: any[]) => void>>();
  const emit = (event: string, ...args: any[]) => handlers.get(event)?.forEach((h) => h(...args));
  return {
    send: (msg) => {
      if (msg?.type !== "infinite_request") return;
      const pa: PayloadArgs = msg.payload_args;
      onRequest(pa);
      const data = sortRows(ROWS, pa.sort, pa.sort_direction).slice(pa.start, pa.end);
      setTimeout(() => emit("msg:custom",
        { type: "infinite_resp", key: pa, length: ROWS.length, payload: { format: "json", data } }, []), 0);
    },
    get: () => undefined,
    set: () => {},
    save_changes: () => {},
    on: (event, h) => {
      if (!handlers.has(event)) handlers.set(event, new Set());
      handlers.get(event)!.add(h);
    },
    off: (event, h) => { handlers.get(event)?.delete(h); },
  };
};

const SortedView: React.FC<{ sort?: HeaderSort }> = ({ sort }) => {
  const [firstRequest, setFirstRequest] = useState<PayloadArgs | null>(null);
  const [sortChanges, setSortChanges] = useState<Array<HeaderSort | null>>([]);
  const model = useMemo(() => makeFakeModel((pa) => setFirstRequest((prev) => prev ?? pa)), []);
  return (
    <div style={{ width: 600 }}>
      <div style={{ height: 300 }}>
        <BuckarooView
          model={model}
          initialState={initialState}
          mode="viewer"
          sort={sort}
          onSortChange={(s) => setSortChanges((prev) => [...prev, s])}
        />
      </div>
      <pre data-testid="first-request">
        {firstRequest
          ? JSON.stringify({ sort: firstRequest.sort ?? null, sort_direction: firstRequest.sort_direction ?? null })
          : ""}
      </pre>
      <pre data-testid="sort-changes">{JSON.stringify(sortChanges)}</pre>
    </div>
  );
};

const meta = {
  title: "Buckaroo/Server/BuckarooViewSort",
  component: SortedView,
  parameters: {
    layout: "centered",
  },
} satisfies Meta<typeof SortedView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const HostSort: Story = {
  args: { sort: { column: "fare", direction: "desc" } },
};
