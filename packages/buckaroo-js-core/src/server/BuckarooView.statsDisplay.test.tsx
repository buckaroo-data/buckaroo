/**
 * The display config a final stats_update carries reaches the AG-Grid column
 * definitions: a float column's minWidth reads its min and max, so the config
 * built from the schema tier and the one built from the full stats differ there.
 * A real WebSocketModel and the real widget, with AgGridReact stubbed by the spy.
 */
import { act, cleanup, render } from "@testing-library/react";
import { BuckarooView } from "./BuckarooView";
import { WebSocketModel } from "./WebSocketModel";
import { getSpyCalls, resetSpy } from "../test-utils/agGridSpy";

jest.mock("ag-grid-react", () => require("../test-utils/agGridSpy").agGridReactMockFactory());
jest.mock("../components/useColorScheme", () => ({ useColorScheme: () => "light" }));
jest.mock("../components/StatusBar", () => ({ StatusBar: () => <div data-testid="status-bar-stub" /> }));

class FakeSocket {
    readyState = 1;
    onmessage: ((e: MessageEvent) => void) | null = null;
    send() {}
    deliver(msg: object) {
        this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
    }
}

const displayArgs = (minWidth: number) => ({
    main: {
        data_key: "main",
        summary_stats_key: "all_stats",
        df_viewer_config: {
            pinned_rows: [],
            left_col_configs: [],
            column_config: [
                { col_name: "a", header_name: "price", displayer_args: { displayer: "obj" }, ag_grid_specs: { minWidth } },
            ],
        },
    },
});

const settle = () => act(async () => { await new Promise<void>((resolve) => setTimeout(resolve, 0)); });

afterEach(cleanup);

it("a final stats_update's display config reaches the grid's column definitions without remounting it", async () => {
    resetSpy();
    const ws = new FakeSocket();
    const meta = { total_rows: 5, columns: 1, filtered_rows: 5, rows_shown: 5, stats: { status: "pending", tier: "schema", gen: 1 } };
    const initialState = { df_meta: meta, df_data_dict: { main: [], all_stats: [] }, df_display_args: displayArgs(100),
        buckaroo_options: { sampled: [], cleaning_method: [""], post_processing: [""], df_display: ["main"], show_commands: [] },
        buckaroo_state: { sampled: false, cleaning_method: false, quick_command_args: {}, post_processing: false, df_display: "main", show_commands: false },
        command_config: { argspecs: {}, defaultArgs: {} } };
    const model = new WebSocketModel(ws as unknown as WebSocket, initialState);

    await act(async () => {
        render(<BuckarooView model={model} initialState={initialState} mode="buckaroo" />);
    });
    const minWidth = () => getSpyCalls().lastProps.columnDefs.find((c: any) => c.field === "a")?.minWidth;
    expect(minWidth()).toBe(100);
    const mounts = getSpyCalls().mountCount;

    ws.deliver({ type: "stats_update", stats_gen: 1, scope: "raw", tier: "full", final: true,
        payload: { format: "json", layout: "wide", data: [{ index: "max", level_0: "max", a: 1e9 }] },
        df_display_args: displayArgs(135) });
    await settle();

    expect(minWidth()).toBe(135);
    expect(getSpyCalls().mountCount).toBe(mounts);
});
