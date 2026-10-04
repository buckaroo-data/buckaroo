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

const renderBar = (dfMeta: DFMeta, onComputeStats?: () => void) =>
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
    const cell = (value: DFMetaStats | undefined, onComputeStats?: () => void) =>
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
        expect(onComputeStats).toHaveBeenCalledTimes(1);
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
