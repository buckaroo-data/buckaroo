/**
 * StatusBar — in-flight indicator (issue #813).
 *
 * After the user changes search / cleaning / post-processing, the status bar
 * must visibly distinguish "computed and final" from "still in flight". An
 * empty grid is otherwise ambiguous between "filter returned zero rows" and
 * "filter is still computing" — a real pain on slow xorq backends.
 */
import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";

// StatusBar mounts an AG-Grid. We don't care about the grid's internals here —
// we only care about the in-flight indicator that lives in the surrounding
// status-bar chrome. Stub AG-Grid out (mirrors the pattern used in
// BuckarooInfiniteWidget.flash.test.tsx).
jest.mock("ag-grid-react", () => ({
    AgGridReact: () => <div data-testid="status-bar-aggrid-stub" />,
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
