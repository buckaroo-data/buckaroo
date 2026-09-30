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
// Props each stub was last rendered with, so tests can check what BuckarooView
// hands the widget.
const mockWidgetProps: { buckaroo?: any; viewer?: any } = {};
jest.mock("../components/BuckarooWidgetInfinite", () => ({
    BuckarooInfiniteWidget: (props: any) => {
        mockWidgetProps.buckaroo = props;
        return <div data-testid="buckaroo-widget-stub" />;
    },
    DFViewerInfiniteDS: (props: any) => {
        mockWidgetProps.viewer = props;
        return <div data-testid="viewer-widget-stub" />;
    },
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

afterEach(() => cleanup());

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

describe("BuckarooView host sort (#984)", () => {
    const initialState = {
        df_meta: { total_rows: 1, columns: 1, filtered_rows: 1, rows_shown: 1 },
        df_data_dict: {},
        df_display_args: { main: { data_key: "main", df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" } },
    };
    const byFare = { column: "fare", direction: "desc" } as const;
    const byName = { column: "name", direction: "asc" } as const;

    beforeEach(() => {
        delete mockWidgetProps.buckaroo;
        delete mockWidgetProps.viewer;
    });

    it.each([
        ["viewer", "viewer"],
        ["buckaroo", "buckaroo"],
    ] as const)("hands sort to the %s widget as initial_sort, and ignores later changes to the prop", async (mode, key) => {
        const { model } = makeFakeModel();
        let result: ReturnType<typeof render>;
        await act(async () => {
            result = render(<BuckarooView model={model} initialState={initialState} mode={mode} sort={byFare} />);
        });
        expect(mockWidgetProps[key].initial_sort).toEqual(byFare);

        await act(async () => {
            result!.rerender(<BuckarooView model={model} initialState={initialState} mode={mode} sort={byName} />);
        });
        expect(mockWidgetProps[key].initial_sort).toEqual(byFare);
    });

    it("passes the widget's sort changes to onSortChange", async () => {
        const { model } = makeFakeModel();
        const onSortChange = jest.fn();
        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="viewer" onSortChange={onSortChange} />);
        });
        act(() => mockWidgetProps.viewer.on_sort_change(byName));
        expect(onSortChange).toHaveBeenLastCalledWith(byName);
        act(() => mockWidgetProps.viewer.on_sort_change(null));
        expect(onSortChange).toHaveBeenLastCalledWith(null);
    });

    it("starts a remounted grid from the last sort the grid reported, not the original prop", async () => {
        // BuckarooInfiniteWidget remounts its grid when operations, cleaning or
        // post-processing change. The new grid has to come up with the sort the
        // host was last told about, or the host's copy (say, in a URL) goes stale.
        const { model } = makeFakeModel();
        let result: ReturnType<typeof render>;
        const view = () => <BuckarooView model={model} initialState={initialState} mode="buckaroo" sort={byFare} />;
        await act(async () => {
            result = render(view());
        });
        act(() => mockWidgetProps.buckaroo.on_sort_change(byName));
        await act(async () => {
            result!.rerender(view());
        });
        expect(mockWidgetProps.buckaroo.initial_sort).toEqual(byName);

        act(() => mockWidgetProps.buckaroo.on_sort_change(null));
        await act(async () => {
            result!.rerender(view());
        });
        expect(mockWidgetProps.buckaroo.initial_sort).toBeUndefined();
    });
});
