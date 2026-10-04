/**
 * StatsEmptyState — the summary view of a session whose stats are not computed
 * (rows-first c5).
 *
 * The summary view lists stats, and there are none to list, so it shows why
 * and offers the control that asks for them: one button for the smallest tier
 * the server allows (basic before full), with a per-column form. When the
 * server's ceiling refuses the stats the view says so and offers nothing.
 */
import "@testing-library/jest-dom";
import { render, screen, fireEvent, within } from "@testing-library/react";

jest.mock("./useColorScheme", () => ({ useColorScheme: () => "light" }));

import { StatsEmptyState, StatsColumnOption, formatStatsEstimate } from "./StatsEmptyState";
import { DFMetaStats } from "./WidgetTypes";

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

const columns: StatsColumnOption[] = [
    { field: "a", label: "name" },
    { field: "b", label: "age" },
];

const renderState = (stats: DFMetaStats, onComputeStats?: jest.Mock, cols: StatsColumnOption[] = columns) =>
    render(<StatsEmptyState stats={stats} columns={cols} onComputeStats={onComputeStats} />);

describe("StatsEmptyState", () => {
    it("size: says the stats were not computed because the table is large, and how large", () => {
        renderState(policy(), jest.fn());
        const root = screen.getByTestId("stats-empty-state");
        expect(root).toHaveAttribute("data-stats-reason", "size");
        expect(root).toHaveTextContent("not computed");
        expect(root).toHaveTextContent("12.4M rows x 44 columns");
    });

    it("offers one button for the smallest tier the server allows, and it calls the handler with no arguments", () => {
        const onComputeStats = jest.fn();
        renderState(policy(), onComputeStats);
        expect(screen.getAllByRole("button")).toHaveLength(1);
        fireEvent.click(screen.getByRole("button", { name: "Compute basic stats" }));
        expect(onComputeStats).toHaveBeenCalledTimes(1);
        expect(onComputeStats).toHaveBeenCalledWith();
    });

    it("names full when it is the only tier left to ask for", () => {
        renderState(policy({ requestable: ["full"] }), jest.fn());
        expect(screen.getByRole("button", { name: "Compute full stats" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Compute basic stats" })).not.toBeInTheDocument();
    });

    it("names full once the basic tier has been reached", () => {
        renderState(policy({ tier: "scalar" }), jest.fn());
        expect(screen.getByRole("button", { name: "Compute full stats" })).toBeInTheDocument();
    });

    it("has a per-column form: the button asks for the column picked, and all columns by default", () => {
        const onComputeStats = jest.fn();
        renderState(policy(), onComputeStats);
        const picker = screen.getByRole("combobox", { name: "Columns to compute" });
        expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["All columns", "name", "age"]);

        fireEvent.change(picker, { target: { value: "b" } });
        fireEvent.click(screen.getByRole("button", { name: "Compute basic stats" }));
        expect(onComputeStats).toHaveBeenLastCalledWith({ columns: ["b"] });

        fireEvent.change(picker, { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: "Compute basic stats" }));
        expect(onComputeStats).toHaveBeenLastCalledWith();
    });

    it("has no per-column picker when it knows no columns", () => {
        renderState(policy(), jest.fn(), []);
        expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Compute basic stats" })).toBeInTheDocument();
    });

    it("ceiling: says the table is over the size limit, and offers no control even with a handler", () => {
        renderState(policy({ reason: "ceiling", requestable: [] }), jest.fn());
        const root = screen.getByTestId("stats-empty-state");
        expect(root).toHaveAttribute("data-stats-reason", "ceiling");
        expect(root).toHaveTextContent("over the size limit");
        expect(root).toHaveTextContent("12.4M rows x 44 columns");
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
        expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    });

    it("ceiling: offers no control whatever requestable lists", () => {
        renderState(policy({ reason: "ceiling", requestable: ["scalar", "full"] }), jest.fn());
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("host: says the stats were turned off, and offers the control", () => {
        renderState(policy({ reason: "host" }), jest.fn());
        expect(screen.getByTestId("stats-empty-state")).toHaveTextContent("turned off");
        expect(screen.getByRole("button", { name: "Compute basic stats" })).toBeInTheDocument();
    });

    it("cost: says the run was paused, and the button reads Continue", () => {
        const onComputeStats = jest.fn();
        renderState(policy({ reason: "cost" }), onComputeStats);
        expect(screen.getByTestId("stats-empty-state")).toHaveTextContent("paused");
        fireEvent.click(screen.getByRole("button", { name: "Continue computing stats" }));
        expect(onComputeStats).toHaveBeenCalledTimes(1);
    });

    it("with no handler it is the message alone", () => {
        renderState(policy());
        expect(screen.getByTestId("stats-empty-state")).toHaveTextContent("not computed");
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("leaves the size out when the server sent no estimate", () => {
        renderState(policy({ estimate: undefined }), jest.fn());
        expect(screen.getByTestId("stats-empty-state")).not.toHaveTextContent("rows");
    });

    it("an older server's not_computed (no policy fields) gets the message and a full-stats button", () => {
        renderState({ status: "not_computed", tier: "schema", gen: 1, reason: "host" }, jest.fn());
        expect(screen.getByRole("button", { name: "Compute full stats" })).toBeInTheDocument();
    });
});

describe("formatStatsEstimate", () => {
    it.each([
        [{ rows: 12_400_000, cols: 44 }, "12.4M rows x 44 columns"],
        [{ rows: 78_000_000 }, "78M rows"],
        [{ rows: 1_000_000 }, "1M rows"],
        [{ rows: 999_999 }, "999,999 rows"],
        [{ rows: 1 }, "1 row"],
        [{ rows: 3, cols: 1 }, "3 rows x 1 column"],
        [{ cols: 44 }, "44 columns"],
        [{}, ""],
        [undefined, ""],
    ])("%j reads %j", (estimate, expected) => {
        expect(formatStatsEstimate(estimate)).toBe(expected);
    });
});
