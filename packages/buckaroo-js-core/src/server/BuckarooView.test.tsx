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
import { decodeDFDataDict } from "../components/DFViewerParts/resolveDFData";

// Stub the heavy widget surfaces — this test exercises the injection
// wiring, not AG-Grid. The widget components instantiate AgGridReact which
// is fragile under jsdom; the stub keeps the test focused on the model
// contract.
//
// The viewer stub records the props BuckarooView hands it, so the rows-first
// tests below can see which df_meta / df_data_dict reached the widget.
const mockViewerProps: any[] = [];
jest.mock("../components/BuckarooWidgetInfinite", () => ({
    BuckarooInfiniteWidget: () => <div data-testid="buckaroo-widget-stub" />,
    DFViewerInfiniteDS: (props: any) => {
        mockViewerProps.push(props);
        return <div data-testid="viewer-widget-stub" />;
    },
    getKeySmartRowCache: jest.fn(() => ({ __stub: "row-cache" })),
}));

// Wrap decodeDFDataDict in a jest.fn that defaults to the real decoder, so the
// existing tests run unchanged and the rows-first tests can count and delay
// decodes.
jest.mock("../components/DFViewerParts/resolveDFData", () => {
    const actual = jest.requireActual("../components/DFViewerParts/resolveDFData");
    return { ...actual, decodeDFDataDict: jest.fn(actual.decodeDFDataDict) };
});

function makeFakeModel(): { model: IModel; events: Map<string, Set<Function>>; sent: any[]; state: Record<string, unknown> } {
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
    return { model, events, sent, state };
}

afterEach(() => {
    mockViewerProps.length = 0;
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

// Rows-first c0a: a second message can follow the first at any moment, so the
// view has to cope with changes that land while it is still wiring itself up.
describe("BuckarooView two-message hardening (rows-first c0a)", () => {
    const mockDecode = decodeDFDataDict as jest.Mock;
    const realDecode = jest.requireActual("../components/DFViewerParts/resolveDFData").decodeDFDataDict;

    const displayArgs = {
        main: { df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" },
    };
    const metaWith = (total_rows: number) => ({ total_rows, columns: 1, filtered_rows: total_rows, rows_shown: total_rows });
    const emit = (events: Map<string, Set<Function>>, name: string, ...args: unknown[]) => {
        for (const h of Array.from(events.get(name) ?? [])) h(...args);
    };
    const lastProps = () => mockViewerProps[mockViewerProps.length - 1];

    beforeEach(() => {
        mockDecode.mockReset();
        mockDecode.mockImplementation(realDecode);
    });

    it("applies a change that reached the model before the effect subscribed", async () => {
        // initialState is what the host held when it built the view. A second
        // initial_state then landed on the model while React was committing,
        // so its change:* events had no listener yet.
        const { model, state } = makeFakeModel();
        state.df_meta = metaWith(99);
        const initialState = { df_meta: metaWith(1), df_data_dict: {}, df_display_args: displayArgs };

        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="viewer" />);
        });

        expect(lastProps().df_meta.total_rows).toBe(99);
    });

    it("decodes a df_data_dict that reached the model before the effect subscribed", async () => {
        const { model, state } = makeFakeModel();
        const raw = { format: "mock", id: "N" };
        state.df_data_dict = { main: raw };
        mockDecode.mockImplementation(async (dict: any) => ({ main: [{ index: 0, from: dict.main.id }] }));
        const initialState = { df_meta: metaWith(1), df_data_dict: {}, df_display_args: displayArgs };

        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="viewer" />);
        });

        expect(lastProps().df_data_dict.main).toEqual([{ index: 0, from: "N" }]);
    });

    it("decodes one initial_state that carries metadata once, and renders its df_data_dict once", async () => {
        const { model, events, state } = makeFakeModel();
        const initialState = { df_meta: metaWith(1), df_data_dict: {}, df_display_args: displayArgs };
        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="viewer" />);
        });
        const dictsBefore = new Set(mockViewerProps.map((p) => p.df_data_dict));
        mockDecode.mockClear();
        mockDecode.mockImplementation(async (dict: any) => ({ main: [{ index: 0, from: dict.main.id }] }));

        // The order WebSocketModel emits for a full frame: one change per key,
        // then "metadata". The model state already holds the new values.
        const frame = {
            df_meta: metaWith(7),
            df_data_dict: { main: { format: "mock", id: "F" } },
            df_display_args: displayArgs,
            metadata: { path: "/data/f.parquet", rows: 7 },
        };
        Object.assign(state, frame);
        await act(async () => {
            emit(events, "change:df_meta", frame.df_meta);
            emit(events, "change:df_data_dict", frame.df_data_dict);
            emit(events, "change:df_display_args", frame.df_display_args);
            emit(events, "metadata", frame.metadata, undefined);
        });

        expect(mockDecode).toHaveBeenCalledTimes(1);
        const dictsAfter = new Set(mockViewerProps.map((p) => p.df_data_dict));
        expect(dictsAfter.size - dictsBefore.size).toBe(1);
        expect(lastProps().df_meta.total_rows).toBe(7);
    });

    it("applies the newer df_data_dict when decodes complete out of order", async () => {
        const { model, events } = makeFakeModel();
        const initialState = { df_meta: metaWith(1), df_data_dict: {}, df_display_args: displayArgs };
        await act(async () => {
            render(<BuckarooView model={model} initialState={initialState} mode="viewer" />);
        });

        const finish: Record<string, () => void> = {};
        mockDecode.mockImplementation(
            (dict: any) =>
                new Promise((resolve) => {
                    finish[dict.main.id] = () => resolve({ main: [{ index: 0, from: dict.main.id }] });
                }),
        );
        await act(async () => {
            emit(events, "change:df_data_dict", { main: { format: "mock", id: "older" } });
            emit(events, "change:df_data_dict", { main: { format: "mock", id: "newer" } });
        });
        // The newer decode finishes first, then the stale one.
        await act(async () => { finish["newer"](); });
        await act(async () => { finish["older"](); });

        expect(lastProps().df_data_dict.main).toEqual([{ index: 0, from: "newer" }]);
    });
});
