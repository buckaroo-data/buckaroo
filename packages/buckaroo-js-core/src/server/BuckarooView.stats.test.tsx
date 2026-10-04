/**
 * BuckarooView — the Compute summary stats control (rows-first c4).
 *
 * While df_meta.stats says the stats are not computed, the status bar offers a
 * control that asks the server for them. BuckarooView hands the widget the
 * callback, and the callback sends `stats_request {force: true, tier}` through
 * whatever IModel the host gave it, with the tier taken from df_meta.stats
 * (rows-first c5). The grid reports the columns it shows, and BuckarooView
 * keeps them on the model, where the scheduler's requests read their hint.
 */
import { render, cleanup, act } from "@testing-library/react";
import { BuckarooView } from "./BuckarooView";
import type { IModel } from "./IModel";

const mockWidgetProps: any[] = [];
jest.mock("../components/BuckarooWidgetInfinite", () => ({
    BuckarooInfiniteWidget: (props: any) => {
        mockWidgetProps.push(props);
        return <div data-testid="buckaroo-widget-stub" />;
    },
    DFViewerInfiniteDS: () => <div data-testid="viewer-widget-stub" />,
    getKeySmartRowCache: jest.fn(() => ({ __stub: "row-cache" })),
}));

function makeFakeModel(state: Record<string, unknown>): { model: IModel; sent: any[] } {
    const sent: any[] = [];
    const model: IModel = {
        send: (msg) => { sent.push(msg); },
        get: (k) => state[k],
        set: (k, v) => { state[k] = v; },
        save_changes: () => {},
        on: () => {},
        off: () => {},
    };
    return { model, sent };
}

const displayArgs = {
    main: { df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] }, summary_stats_key: "all_stats" },
};
const metaWith = (stats?: Record<string, unknown>) => ({
    total_rows: 3, columns: 1, filtered_rows: 3, rows_shown: 3,
    ...(stats === undefined ? {} : { stats }),
});

const mountBuckaroo = async (state: Record<string, unknown>) => {
    const { model, sent } = makeFakeModel(state);
    await act(async () => {
        render(<BuckarooView model={model} initialState={state} mode="buckaroo" />);
    });
    return { model, sent, props: () => mockWidgetProps[mockWidgetProps.length - 1] };
};

afterEach(() => {
    mockWidgetProps.length = 0;
    cleanup();
});

describe("BuckarooView on_compute_stats (rows-first c4)", () => {
    it("hands the widget a callback that sends a forced stats_request for the gen on screen", async () => {
        const { sent, props } = await mountBuckaroo({
            df_meta: metaWith({ status: "not_computed", tier: "schema", gen: 9 }),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        expect(typeof props().on_compute_stats).toBe("function");

        props().on_compute_stats();
        // A time-boxed step, like the scheduler's (rows-first c4b), for the one
        // tier a server that names none can be asked for (rows-first c5).
        expect(sent).toEqual([
            { type: "stats_request", stats_gen: 9, scope: "raw", incremental: true, force: true, tier: "full" },
        ]);
    });

    it("takes the tier from df_meta.stats.requestable: scalar before full", async () => {
        const { sent, props } = await mountBuckaroo({
            df_meta: metaWith({ status: "not_computed", tier: "schema", gen: 9, requestable: ["scalar", "full"] }),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        props().on_compute_stats();
        expect(sent).toEqual([
            { type: "stats_request", stats_gen: 9, scope: "raw", incremental: true, force: true, tier: "scalar" },
        ]);
    });

    it("hands the per-column form's columns on to the request", async () => {
        const { sent, props } = await mountBuckaroo({
            df_meta: metaWith({ status: "not_computed", tier: "schema", gen: 9, requestable: ["scalar", "full"] }),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        props().on_compute_stats({ columns: ["b"] });
        expect(sent).toEqual([
            { type: "stats_request", stats_gen: 9, scope: "raw", incremental: true, force: true, tier: "scalar", columns: ["b"] },
        ]);
    });

    it("sends nothing when the server left no tier to ask for", async () => {
        const { sent, props } = await mountBuckaroo({
            df_meta: metaWith({ status: "not_computed", tier: "schema", gen: 9, reason: "ceiling", requestable: [] }),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        props().on_compute_stats();
        expect(sent).toEqual([]);
    });

    it("records the columns the grid shows on the model, and the whole-table control does not send them", async () => {
        const { model, sent, props } = await mountBuckaroo({
            df_meta: metaWith({ status: "not_computed", tier: "schema", gen: 9 }),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        expect(typeof props().on_visible_columns).toBe("function");

        props().on_visible_columns(["a", "b"]);
        expect(model.get("visible_columns")).toEqual(["a", "b"]);
        props().on_compute_stats();
        // On a forced request `columns` names what it is for, so the hint stays off.
        expect(sent).toEqual([
            { type: "stats_request", stats_gen: 9, scope: "raw", incremental: true, force: true, tier: "full" },
        ]);
    });

    it("sends nothing when the model's df_meta carries no stats.gen", async () => {
        const { sent, props } = await mountBuckaroo({
            df_meta: metaWith(),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        expect(typeof props().on_compute_stats).toBe("function");
        props().on_compute_stats();
        expect(sent).toEqual([]);
    });

    it("sends no request on its own: asking is the scheduler's job, and a session that is not pending is left alone", async () => {
        const { sent } = await mountBuckaroo({
            df_meta: metaWith({ status: "not_computed", tier: "schema", gen: 9 }),
            df_data_dict: {},
            df_display_args: displayArgs,
        });
        expect(sent).toEqual([]);
    });
});
