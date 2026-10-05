/**
 * StatusBar — summary stats status (rows-first c4).
 *
 * A session that reports df_meta.stats gets one extra, fixed-width column in
 * the status bar showing where the stats stand: loading ("pending"), not
 * computed (with a control that asks for them), error (with the reason) or
 * ready. A session that does not report df_meta.stats gets the status bar it
 * always had.
 *
 * AG Grid is stubbed to capture the props the status bar hands it; the cell
 * renderer is rendered on its own.
 */
import "@testing-library/jest-dom";
import { render, screen, fireEvent } from "@testing-library/react";

// The props the status bar gave AG Grid on its last render.
const mockGrid: { props: any } = { props: null };
jest.mock("ag-grid-react", () => ({
    AgGridReact: (props: any) => {
        // React also calls this stub once with no props; keep the last real ones.
        if (props) mockGrid.props = props;
        return <div data-testid="status-bar-aggrid-stub" />;
    },
}));
jest.mock("./useColorScheme", () => ({ useColorScheme: () => "light" }));

import { StatusBar, StatsStatusCell } from "./StatusBar";
import { BuckarooOptions, BuckarooState, DFMeta, DFMetaStats } from "./WidgetTypes";

const baseMeta: DFMeta = { total_rows: 378, columns: 7, filtered_rows: 297, rows_shown: 297 };
const options: BuckarooOptions = {
    sampled: [],
    cleaning_method: ["", "clean1"],
    post_processing: ["", "post1"],
    df_display: ["main", "summary"],
    show_commands: ["0", "1"],
};
const bState: BuckarooState = {
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
};

const renderBar = (dfMeta: DFMeta, onComputeStats?: (opts?: { columns?: string[] }) => void) =>
    render(
        <StatusBar
            dfMeta={dfMeta}
            buckarooState={bState}
            setBuckarooState={() => {}}
            buckarooOptions={options}
            onComputeStats={onComputeStats}
        />,
    );

const fields = (): string[] => mockGrid.props.columnDefs.map((c: any) => c.field);

describe("StatusBar stats column", () => {
    beforeEach(() => {
        mockGrid.props = null;
    });

    it("adds no column and no row field when df_meta has no stats (every session today)", () => {
        renderBar(baseMeta);
        expect(fields()).not.toContain("stats");
        expect(mockGrid.props.rowData[0]).not.toHaveProperty("stats");
    });

    it("adds a fixed-width stats column after the summary-view selector when df_meta.stats is present", () => {
        const stats: DFMetaStats = { status: "pending", tier: "schema", gen: 1 };
        renderBar({ ...baseMeta, stats });
        const names = fields();
        expect(names.indexOf("stats")).toBe(names.indexOf("df_display") + 1);

        const column = mockGrid.props.columnDefs[names.indexOf("stats")];
        expect(column.cellRenderer).toBe(StatsStatusCell);
        // A fixed width, so the status changing never moves the other columns.
        expect(typeof column.width).toBe("number");
        expect(column.flex).toBeUndefined();
        expect(mockGrid.props.rowData[0].stats).toBe(stats);
    });

    it("keeps the column for every status", () => {
        for (const status of ["pending", "not_computed", "error", "complete"] as const) {
            const { unmount } = renderBar({ ...baseMeta, stats: { status, gen: 1 } });
            expect(fields()).toContain("stats");
            unmount();
        }
    });

    it("hands the compute callback to the cell renderer through the grid context", () => {
        const onComputeStats = jest.fn();
        renderBar({ ...baseMeta, stats: { status: "not_computed", gen: 1 } }, onComputeStats);
        expect(mockGrid.props.context.onComputeStats).toBe(onComputeStats);
    });
});

describe("StatsStatusCell", () => {
    const cell = (value: DFMetaStats | undefined, onComputeStats?: (opts?: { columns?: string[] }) => void) =>
        render(<StatsStatusCell value={value} context={{ onComputeStats }} />);

    it("pending: says the stats are being computed", () => {
        cell({ status: "pending", gen: 1 });
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-status", "pending");
        expect(root).toHaveTextContent("Computing summary stats");
        expect(root).toHaveAttribute("role", "status");
    });

    it("not_computed: offers a Compute summary stats button that calls the handler", () => {
        const onComputeStats = jest.fn();
        cell({ status: "not_computed", gen: 1 }, onComputeStats);
        expect(screen.getByTestId("stats-status")).toHaveAttribute("data-stats-status", "not_computed");

        fireEvent.click(screen.getByRole("button", { name: "Compute summary stats" }));
        // Called with no arguments, not with the click event.
        expect(onComputeStats).toHaveBeenCalledTimes(1);
        expect(onComputeStats).toHaveBeenCalledWith();
    });

    it("not_computed: with no handler there is no button, only the label", () => {
        cell({ status: "not_computed", gen: 1 });
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Summary stats not computed");
    });

    it("error: shows the reason", () => {
        cell({ status: "error", gen: 1, reason: "stats_failed" });
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-status", "error");
        expect(root).toHaveTextContent("Stats error: stats_failed");
    });

    it("error: without a reason still says so", () => {
        cell({ status: "error", gen: 1 });
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Stats error");
    });

    it("complete: says the stats are ready", () => {
        cell({ status: "complete", tier: "full", gen: 1 });
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-status", "complete");
        expect(root).toHaveTextContent("Summary stats ready");
    });

    it("renders nothing without stats", () => {
        const { container } = cell(undefined);
        expect(container).toBeEmptyDOMElement();
    });
});

// The server's policy fields say why the stats were not computed and what may
// still be asked for (rows-first c5).
describe("StatsStatusCell, not computed by policy (rows-first c5)", () => {
    const policy = (over: Partial<DFMetaStats> = {}): DFMetaStats => ({
        status: "not_computed",
        tier: "schema",
        gen: 1,
        reason: "size",
        tier_target: "schema",
        estimate: { rows: 12_400_000, cols: 44 },
        auto_request: false,
        requestable: ["scalar", "full"],
        ...over,
    });
    const cell = (value: DFMetaStats | undefined, onComputeStats?: (opts?: { columns?: string[] }) => void) =>
        render(<StatsStatusCell value={value} context={{ onComputeStats }} />);

    it("size: offers the control, and says how large the table is in its title", () => {
        const onComputeStats = jest.fn();
        cell(policy(), onComputeStats);
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-status", "not_computed");
        expect(root).toHaveAttribute("data-stats-reason", "size");

        const button = screen.getByRole("button", { name: "Compute summary stats" });
        expect(button).toHaveAttribute("title", expect.stringContaining("12.4M rows"));
        fireEvent.click(button);
        // The whole table, with no arguments: the wiring picks the tier from df_meta.
        expect(onComputeStats).toHaveBeenCalledTimes(1);
        expect(onComputeStats).toHaveBeenCalledWith();
    });

    it("host: offers the control", () => {
        cell(policy({ reason: "host" }), jest.fn());
        expect(screen.getByRole("button", { name: "Compute summary stats" })).toBeInTheDocument();
    });

    it("cost: the control reads Continue, since the run was paused", () => {
        const onComputeStats = jest.fn();
        cell(policy({ reason: "cost" }), onComputeStats);
        expect(screen.queryByRole("button", { name: "Compute summary stats" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Continue computing stats" }));
        expect(onComputeStats).toHaveBeenCalledTimes(1);
    });

    it("ceiling: a message and no control, even with a handler and a requestable list", () => {
        cell(policy({ reason: "ceiling" }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-reason", "ceiling");
        expect(root).toHaveTextContent("Summary stats unavailable");
        expect(root).toHaveAttribute("title", expect.stringContaining("size limit"));
    });

    it("nothing requestable for a size the server chose: it is at the ceiling, so the message and no control", () => {
        cell(policy({ requestable: [] }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Summary stats unavailable");
    });

    it("nothing requestable for a host's choice: the label only", () => {
        cell(policy({ reason: "host", requestable: [] }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Summary stats not computed");
    });

    it("an older server's not_computed (no policy fields) still offers the control", () => {
        cell({ status: "not_computed", tier: "schema", gen: 1, reason: "host" }, jest.fn());
        expect(screen.getByRole("button", { name: "Compute summary stats" })).toBeInTheDocument();
    });

    it("keeps the label for the other statuses whatever the reason says", () => {
        cell({ status: "complete", tier: "full", gen: 1, reason: "ceiling" } as DFMetaStats, jest.fn());
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Summary stats ready");
    });
});

// A session that is not computed can have a run for the whole table behind it
// (rows-first c5b): the client records the tier its final reply reached in
// df_meta.stats.reached_tier, since the server's `tier` stays at schema. The
// cell says which tier is on screen, offers the control only while a tier above
// it is left, and otherwise says the stats are computed.
describe("StatsStatusCell, tier reached (rows-first c5b)", () => {
    const reached = (over: Partial<DFMetaStats> = {}): DFMetaStats => ({
        status: "not_computed",
        tier: "schema",
        gen: 1,
        reason: "size",
        tier_target: "schema",
        estimate: { rows: 12_400_000, cols: 44 },
        auto_request: false,
        requestable: ["scalar", "full"],
        reached_tier: "scalar",
        ...over,
    });
    const cell = (value: DFMetaStats | undefined, onComputeStats?: (opts?: { columns?: string[] }) => void) =>
        render(<StatsStatusCell value={value} context={{ onComputeStats }} />);

    it("after scalar, with full left: says basic stats are shown, and the control now asks for full", () => {
        const onComputeStats = jest.fn();
        cell(reached(), onComputeStats);
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-status", "not_computed");
        expect(root).toHaveTextContent("Basic stats");
        // The button is not the one the session started with.
        expect(screen.queryByRole("button", { name: "Compute summary stats" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Compute full stats" }));
        expect(onComputeStats).toHaveBeenCalledTimes(1);
        expect(onComputeStats).toHaveBeenCalledWith();
    });

    it("after scalar on a session the server sized to scalar (requestable absent, so full is left)", () => {
        cell(reached({ tier_target: "scalar", auto_request: undefined, requestable: undefined }), jest.fn());
        expect(screen.getByRole("button", { name: "Compute full stats" })).toBeInTheDocument();
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Basic stats");
    });

    it("after scalar, with nothing above it requestable: the control is replaced by a label that says which tier", () => {
        cell(reached({ requestable: ["scalar"] }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveAttribute("data-stats-status", "not_computed");
        expect(root).toHaveTextContent("Basic stats computed");
        expect(root).toHaveAttribute("title", expect.stringContaining("min, max"));
    });

    it("after full: the label says the summary stats are computed, with no control", () => {
        cell(reached({ reached_tier: "full" }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Summary stats computed");
    });

    it("the ceiling does not take the label away: scalar stats are on screen", () => {
        cell(reached({ reason: "ceiling" }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        const root = screen.getByTestId("stats-status");
        expect(root).toHaveTextContent("Basic stats computed");
        expect(root).not.toHaveTextContent("unavailable");
    });

    it("a session at its ceiling that was sized to scalar reads as computed once scalar is in, not as unavailable", () => {
        cell(reached({ tier_target: "scalar", requestable: [] }), jest.fn());
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Basic stats computed");
    });

    it("with no handler there is no control to offer, so the label", () => {
        cell(reached());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        expect(screen.getByTestId("stats-status")).toHaveTextContent("Basic stats computed");
    });

});
