/**
 * StatusBar — in-flight indicator (issue #813).
 *
 * After the user changes search / cleaning / post-processing, the status bar
 * must visibly distinguish "computed and final" from "still in flight". An
 * empty grid is otherwise ambiguous between "filter returned zero rows" and
 * "filter is still computing" — a real pain on slow xorq backends.
 */
import "@testing-library/jest-dom";
import { act, render, screen } from "@testing-library/react";

// StatusBar mounts an AG-Grid. We don't care about the grid's internals here —
// we only care about the in-flight indicator that lives in the surrounding
// status-bar chrome, and about the columnDefs / rowData the search cell is
// wired through. Stub AG-Grid out (mirrors the pattern used in
// BuckarooInfiniteWidget.flash.test.tsx) and keep the last props so the
// search tests can drive the search column's onCellValueChanged directly.
const mockGridProps: { current: any } = { current: null };
jest.mock("ag-grid-react", () => ({
    AgGridReact: (props: any) => {
        mockGridProps.current = props;
        return <div data-testid="status-bar-aggrid-stub" />;
    },
}));
jest.mock("./useColorScheme", () => ({ useColorScheme: () => "light" }));

import { StatusBar } from "./StatusBar";
import { BuckarooOptions, BuckarooState, DFMeta } from "./WidgetTypes";

const dfMeta: DFMeta = {
    total_rows: 378,
    columns: 7,
    filtered_rows: 297,
    rows_shown: 297,
};

const buckarooOptions: BuckarooOptions = {
    sampled: [],
    cleaning_method: ["", "clean1"],
    post_processing: ["", "post1"],
    df_display: ["main", "summary"],
    show_commands: ["0", "1"],
};

const buckarooState: BuckarooState = {
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
};

describe("StatusBar in-flight indicator (#813)", () => {
    it("does NOT render the in-flight indicator by default", () => {
        render(
            <StatusBar
                dfMeta={dfMeta}
                buckarooState={buckarooState}
                setBuckarooState={() => {}}
                buckarooOptions={buckarooOptions}
            />
        );
        expect(screen.queryByTestId("status-bar-inflight")).not.toBeInTheDocument();
    });

    it("does NOT render the in-flight indicator when inFlight=false", () => {
        render(
            <StatusBar
                dfMeta={dfMeta}
                buckarooState={buckarooState}
                setBuckarooState={() => {}}
                buckarooOptions={buckarooOptions}
                inFlight={false}
            />
        );
        expect(screen.queryByTestId("status-bar-inflight")).not.toBeInTheDocument();
    });

    it("renders the in-flight indicator when inFlight=true", () => {
        render(
            <StatusBar
                dfMeta={dfMeta}
                buckarooState={buckarooState}
                setBuckarooState={() => {}}
                buckarooOptions={buckarooOptions}
                inFlight={true}
            />
        );
        const indicator = screen.getByTestId("status-bar-inflight");
        expect(indicator).toBeInTheDocument();
        // ARIA — distinguishes "computing" from "no results" for assistive tech
        // as well as the visual indicator. Without aria-live the empty-grid
        // ambiguity persists for screen-reader users.
        expect(indicator).toHaveAttribute("aria-live");
    });
});

/**
 * Live search dispatch (#998).
 *
 * In server mode the search box must set `buckaroo_state.search_string`,
 * the per-client row-only path the server already has (#838), instead of
 * `quick_command_args.search`, which the server treats as a dataflow change
 * (full rerun + stats + broadcast on every keystroke). The Jupyter widget
 * has no server-side row path, so its default stays on quick_command_args.
 */
describe("StatusBar live search dispatch (#998)", () => {
    // The prop doesn't exist yet on main; spread it loosely so the file
    // type-checks while the test is red.
    const rowsMode = { liveSearchMode: "rows" } as Record<string, unknown>;

    const searchColDef = () =>
        mockGridProps.current.columnDefs.find((c: { field?: string }) => c.field === "search");

    // StatusBar may dispatch a value or a functional updater; resolve either
    // against the state the cell was rendered with.
    const resolveDispatched = (setter: jest.Mock, prev: BuckarooState) => {
        expect(setter).toHaveBeenCalledTimes(1);
        const arg = setter.mock.calls[0][0];
        return typeof arg === "function" ? arg(prev) : arg;
    };

    it("rows mode: a search term sets search_string and leaves quick_command_args untouched", () => {
        const setBuckarooState = jest.fn();
        const state: BuckarooState = { ...buckarooState, quick_command_args: { sort: ["a"] } };
        render(
            <StatusBar
                dfMeta={dfMeta}
                buckarooState={state}
                setBuckarooState={setBuckarooState}
                buckarooOptions={buckarooOptions}
                {...rowsMode}
            />
        );
        act(() => {
            searchColDef().onCellValueChanged({ oldValue: "", newValue: "alle" });
        });
        const next = resolveDispatched(setBuckarooState, state);
        expect(next.search_string).toBe("alle");
        // Same reference: the row-only path must not touch the dataflow
        // fields, or the server reruns the dataflow anyway.
        expect(next.quick_command_args).toBe(state.quick_command_args);
    });

    it("rows mode: the search cell shows buckaroo_state.search_string (overlay round-trip, #854)", () => {
        const state = { ...buckarooState, search_string: "alle" } as BuckarooState;
        render(
            <StatusBar
                dfMeta={dfMeta}
                buckarooState={state}
                setBuckarooState={() => {}}
                buckarooOptions={buckarooOptions}
                {...rowsMode}
            />
        );
        expect(mockGridProps.current.rowData[0].search).toBe("alle");
    });
});
