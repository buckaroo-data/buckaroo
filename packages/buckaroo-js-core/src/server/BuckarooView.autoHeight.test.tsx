/**
 * BuckarooView — autoHeight prop (#846).
 *
 * Hosts that stack multiple BuckarooServerView embeds (notebook-style, one
 * per dataframe) can't pick a one-size embed height: a 4-row aggregate and
 * a 100k-row main frame need very different vertical real estate. The
 * `autoHeight` prop lets hosts opt into AG Grid's `domLayout: "autoHeight"`
 * so the grid grows to its row count instead of filling the parent.
 */
import { render, cleanup, act } from "@testing-library/react";
import { BuckarooView } from "./BuckarooView";
import type { IModel } from "./IModel";

// Capture props passed to the (stubbed) viewer surface so the test can
// inspect what BuckarooView pushed down — that's where the autoHeight
// plumbing has to land.
const capturedDsProps: any[] = [];

jest.mock("../components/BuckarooWidgetInfinite", () => ({
    BuckarooInfiniteWidget: () => <div data-testid="buckaroo-widget-stub" />,
    DFViewerInfiniteDS: (props: any) => {
        capturedDsProps.push(props);
        return <div data-testid="viewer-widget-stub" />;
    },
    getKeySmartRowCache: jest.fn(() => ({ __stub: "row-cache" })),
}));

function makeFakeModel(): IModel {
    const state: Record<string, unknown> = {};
    return {
        send: () => {},
        get: (k) => state[k],
        set: (k, v) => { state[k] = v; },
        save_changes: () => {},
        on: () => {},
        off: () => {},
    };
}

afterEach(() => {
    capturedDsProps.length = 0;
    cleanup();
});

const baseInitialState = () => ({
    df_meta: { total_rows: 4, columns: 2, filtered_rows: 4, rows_shown: 4 },
    df_data_dict: {},
    df_display_args: {
        main: {
            df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] },
            summary_stats_key: "all_stats",
        },
    },
});

describe("BuckarooView autoHeight (#846)", () => {
    it("injects component_config.layoutType='autoHeight' into df_display_args when autoHeight is set", async () => {
        await act(async () => {
            render(
                <BuckarooView
                    model={makeFakeModel()}
                    initialState={baseInitialState()}
                    mode="viewer"
                    autoHeight
                />,
            );
        });

        expect(capturedDsProps.length).toBeGreaterThan(0);
        const last = capturedDsProps[capturedDsProps.length - 1];
        const cc = last.df_display_args.main.df_viewer_config.component_config;
        expect(cc?.layoutType).toBe("autoHeight");
    });

    it("preserves a server-provided layoutType when autoHeight is not set", async () => {
        const state = {
            df_meta: { total_rows: 4, columns: 2, filtered_rows: 4, rows_shown: 4 },
            df_data_dict: {},
            df_display_args: {
                main: {
                    df_viewer_config: {
                        pinned_rows: [],
                        left_col_configs: [],
                        column_config: [],
                        component_config: { layoutType: "normal" },
                    },
                    summary_stats_key: "all_stats",
                },
            },
        };
        await act(async () => {
            render(
                <BuckarooView
                    model={makeFakeModel()}
                    initialState={state}
                    mode="viewer"
                />,
            );
        });

        const last = capturedDsProps[capturedDsProps.length - 1];
        const cc = last.df_display_args.main.df_viewer_config.component_config;
        expect(cc?.layoutType).toBe("normal");
    });

    it("drops height:100% from the wrapper when autoHeight is set, so the grid can grow with its rows", async () => {
        const { container } = render(
            <BuckarooView
                model={makeFakeModel()}
                initialState={baseInitialState()}
                mode="viewer"
                autoHeight
            />,
        );

        const wrapper = container.querySelector(".buckaroo_anywidget") as HTMLElement | null;
        expect(wrapper).not.toBeNull();
        // height:100% would cap the grid inside the parent — the whole point
        // of autoHeight is for the wrapper to size to its contents.
        expect(wrapper!.style.height).not.toBe("100%");
    });
});
