/**
 * BuckarooView — transport-agnostic embed.
 *
 * Pins the contract from #759: a host can mount BuckarooView with a fake
 * IModel and a pre-collected initial_state, and the component renders
 * without ever opening a WebSocket. This is the path Tauri/Electron hosts
 * use when relaying through IPC.
 */
import { render, cleanup, act } from "@testing-library/react";
import { BuckarooView } from "./BuckarooView";
import type { IModel } from "./IModel";

// Stub the heavy widget surfaces — this test exercises the injection
// wiring, not AG-Grid. The widget components instantiate AgGridReact which
// is fragile under jsdom; the stub keeps the test focused on the model
// contract.
const widgetProps: any[] = [];
jest.mock("../components/BuckarooWidgetInfinite", () => ({
    BuckarooInfiniteWidget: (props: any) => {
        widgetProps.push(props);
        return <div data-testid="buckaroo-widget-stub" />;
    },
    DFViewerInfiniteDS: () => <div data-testid="viewer-widget-stub" />,
    getKeySmartRowCache: jest.fn(() => ({ __stub: "row-cache" })),
}));

function makeFakeModel(): { model: IModel; events: Map<string, Set<Function>>; sent: any[] } {
    const events = new Map<string, Set<Function>>();
    const state: Record<string, unknown> = {};
    const sent: any[] = [];
    const model: IModel = {
        send: (msg) => { sent.push(msg); },
        get: (k) => state[k],
        set: (k, v) => { state[k] = v; },
        save_changes: () => { /* noop */ },
        on: (e, h) => {
            if (!events.has(e)) events.set(e, new Set());
            events.get(e)!.add(h);
        },
        off: (e, h) => { events.get(e)?.delete(h); },
    };
    return { model, events, sent };
}

afterEach(() => {
    widgetProps.length = 0;
    cleanup();
});

describe("BuckarooView (injectable IModel — #759)", () => {
    it("renders the viewer widget when given a fake IModel + initialState — no WebSocket needed", async () => {
        const { model, events } = makeFakeModel();
        const initialState = {
            df_meta: { total_rows: 1, columns: 1, filtered_rows: 1, rows_shown: 1 },
            df_data_dict: {},
            df_display_args: { main: { df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" } },
        };

        let result: ReturnType<typeof render>;
        await act(async () => {
            result = render(<BuckarooView model={model} initialState={initialState} mode="viewer" />);
        });
        const { getByTestId } = result!;

        // Renders the viewer (not the full buckaroo widget) per mode prop.
        expect(getByTestId("viewer-widget-stub")).toBeTruthy();

        // The change-event wiring subscribed via the injected model — proves
        // the model is the one driving updates, not an internal WebSocket.
        expect(events.get("change:df_meta")?.size).toBe(1);
        expect(events.get("change:buckaroo_state")?.size).toBe(1);
        expect(events.get("metadata")?.size).toBe(1);
    });

    it("does not hand raw parquet_b64 payloads to the widget on first render (codex P2)", () => {
        const { model } = makeFakeModel();
        const initialState = {
            df_meta: { total_rows: 1, columns: 1, filtered_rows: 1, rows_shown: 1 },
            // Raw payload — what a host adapter would pass straight from the wire.
            df_data_dict: { main: { format: "parquet_b64", data: "ZmFrZQ==" } },
            df_display_args: { main: { df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" } },
        };

        // Render synchronously — no act() wrapper. We want to see the very
        // first commit, before the resolve effect fires.
        const { queryByTestId, getByText } = render(
            <BuckarooView model={model} initialState={initialState} mode="viewer" />,
        );

        // The widget must NOT receive the raw payload — otherwise
        // makeStaticInfiniteDs crashes on data.slice(...).
        expect(queryByTestId("viewer-widget-stub")).toBeNull();
        expect(getByText(/Preparing/)).toBeTruthy();
    });

    it("fires onMetadata for the initial payload", async () => {
        const { model } = makeFakeModel();
        const onMetadata = jest.fn();
        const initialState = {
            df_display_args: { main: { df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" } },
            metadata: { path: "/data/sales.parquet", rows: 42 },
            prompt: "tell me about sales",
        };

        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="viewer" onMetadata={onMetadata} />);
        });

        expect(onMetadata).toHaveBeenCalledWith({ path: "/data/sales.parquet", rows: 42 }, "tell me about sales");
    });
});

describe("BuckarooView live search mode (#998)", () => {
    it("tells BuckarooInfiniteWidget to run live search on the server's row-only path", async () => {
        // The server treats quick_command_args as a dataflow change (rerun +
        // stats + broadcast per keystroke) and has a per-client row-only path
        // keyed on buckaroo_state.search_string (#838). The server entry point
        // is where that choice is made; the Jupyter widget keeps its default.
        const { model } = makeFakeModel();
        const initialState = {
            df_meta: { total_rows: 1, columns: 1, filtered_rows: 1, rows_shown: 1 },
            df_data_dict: {},
            df_display_args: { main: { df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" } },
            buckaroo_state: { sampled: false, cleaning_method: "", quick_command_args: {}, post_processing: "", df_display: "main", show_commands: false, search_string: "" },
            buckaroo_options: { sampled: [], cleaning_method: [""], post_processing: [""], df_display: ["main"], show_commands: ["0", "1"] },
        };

        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="buckaroo" />);
        });

        expect(widgetProps.length).toBeGreaterThan(0);
        expect(widgetProps[widgetProps.length - 1].liveSearchMode).toBe("rows");
    });
});
