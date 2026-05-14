/**
 * Flash matrix — leaf component (DFViewerInfinite).
 *
 * Pins down what AG-Grid sees when each kind of upstream change happens.
 * Tests assert CURRENT behavior on main (Option A in docs/rerender-test-plan.md);
 * the refactor PRs will flip the assertions one by one.
 *
 * Tests that capture today's flash are tagged "[captures current flash]" so it
 * is clear they are tracking pain, not validating it.
 */
import { render } from "@testing-library/react";
import { DFViewerInfinite } from "./DFViewerInfinite";
import { DFViewerConfig } from "./DFWhole";
import { getSpyCalls, resetSpy } from "../../test-utils/agGridSpy";

// jest.mock factory is hoisted; use require() so the factory resolves at call time.
jest.mock("ag-grid-react", () =>
  require("../../test-utils/agGridSpy").agGridReactMockFactory(),
);

jest.mock("../useColorScheme", () => ({
  useColorScheme: () => "light",
}));

const baseConfig: DFViewerConfig = {
  pinned_rows: [{ primary_key_val: "mean", displayer_args: { displayer: "obj" } }],
  left_col_configs: [],
  column_config: [
    { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
    { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
  ],
};

const rawWrapper = (data: any[]) => ({
  data_type: "Raw" as const,
  data,
  length: data.length,
});

const dsWrapper = (length = 50, getRows = jest.fn()) => ({
  data_type: "DataSource" as const,
  length,
  datasource: { rowCount: length, getRows },
});

beforeEach(() => {
  resetSpy();
});

describe("DFViewerInfinite — flash matrix (current behavior)", () => {
  it("post_processing change purges the infinite cache without remounting AG-Grid", () => {
    const { rerender } = render(
      <DFViewerInfinite
        data_wrapper={dsWrapper()}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ post_processing: "noop" }}
      />,
    );
    const calls = getSpyCalls();
    expect(calls.mountCount).toBe(1);
    const purgesBefore = calls.purgeInfiniteCache;

    rerender(
      <DFViewerInfinite
        data_wrapper={dsWrapper()}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ post_processing: "log_scale" }}
      />,
    );
    // Post step-3: the React key on AgGridReact is data_type, not the
    // stringified outside_df_params. A within-data_type content change drives
    // an effect that calls purgeInfiniteCache() instead of remounting the grid.
    expect(getSpyCalls().mountCount).toBe(1);
    expect(getSpyCalls().purgeInfiniteCache).toBeGreaterThan(purgesBefore);
  });

  it("outside_df_params identity-only change (same value, new object) does NOT remount", () => {
    const { rerender } = render(
      <DFViewerInfinite
        data_wrapper={dsWrapper()}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ post_processing: "noop" }}
      />,
    );
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(
      <DFViewerInfinite
        data_wrapper={dsWrapper()}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ post_processing: "noop" }}
      />,
    );
    // JSON.stringify of the same value is the same string, so the React key
    // doesn't change. The widget is correct here even though outside_df_params
    // is a fresh literal each render.
    expect(getSpyCalls().mountCount).toBe(1);
  });

  it("summary_stats_data update calls setGridOption('pinnedTopRowData') without remount", () => {
    const props = {
      data_wrapper: rawWrapper([{ index: 0, a: 1 }]),
      df_viewer_config: baseConfig,
      setActiveCol: jest.fn(),
    };
    const { rerender } = render(
      <DFViewerInfinite {...props} summary_stats_data={[{ index: "mean", a: 10 }]} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(
      <DFViewerInfinite {...props} summary_stats_data={[{ index: "mean", a: 22 }]} />,
    );

    const pinnedCalls = getSpyCalls().setGridOption.filter(([k]) => k === "pinnedTopRowData");
    expect(pinnedCalls.length).toBeGreaterThanOrEqual(2);
    const last = pinnedCalls[pinnedCalls.length - 1][1] as Array<{ a: number }>;
    expect(last[0].a).toBe(22);
    expect(getSpyCalls().mountCount).toBe(1);
  });

  it("Raw data update calls setGridOption('rowData') without remount", () => {
    const props = {
      df_viewer_config: baseConfig,
      summary_stats_data: [],
      setActiveCol: jest.fn(),
    };
    const { rerender } = render(
      <DFViewerInfinite {...props} data_wrapper={rawWrapper([{ index: 0, a: 1 }])} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(
      <DFViewerInfinite {...props} data_wrapper={rawWrapper([{ index: 0, a: 9 }])} />,
    );

    const rowDataCalls = getSpyCalls().setGridOption.filter(([k]) => k === "rowData");
    expect(rowDataCalls.length).toBeGreaterThanOrEqual(1);
    const last = rowDataCalls[rowDataCalls.length - 1][1] as Array<{ a: number }>;
    expect(last[0].a).toBe(9);
    expect(getSpyCalls().mountCount).toBe(1);
  });

  it("getRowId for the same data index is stable across outside_df_params changes", () => {
    const { rerender } = render(
      <DFViewerInfinite
        data_wrapper={dsWrapper()}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ k: "A" }}
      />,
    );
    rerender(
      <DFViewerInfinite
        data_wrapper={dsWrapper()}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ k: "B" }}
      />,
    );
    // Post step-4: getRowId returns just String(index). Same row index → same
    // rowId across outside_df_params changes. AG-Grid recycles the row DOM
    // and does in-place cell-value updates instead of tearing down rows.
    const ids = getSpyCalls().rowIdsByIndex.get(0);
    expect(ids).toBeDefined();
    expect(ids!.size).toBe(1);
    expect([...ids!][0]).toBe("0");
  });

  it("DataSource mode datasource is exercised; sourceName carries outside_df_params", () => {
    render(
      <DFViewerInfinite
        data_wrapper={dsWrapper(50, jest.fn())}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ post_processing: "noop", df_display: "main" }}
      />,
    );
    const grCalls = getSpyCalls().getRowsCallArgs;
    expect(grCalls.length).toBeGreaterThanOrEqual(1);
    // The spy fires getRows with the live context; the consumer's getRows
    // implementation reads context.outside_df_params to build sourceName.
    // We assert the context made it through end-to-end.
    expect(grCalls[0].context?.outside_df_params).toMatchObject({
      post_processing: "noop",
      df_display: "main",
    });
  });

  it("column_config reshape does not cause an AG-Grid remount", () => {
    const cfgA = baseConfig;
    const cfgB: DFViewerConfig = {
      ...baseConfig,
      column_config: [
        ...baseConfig.column_config,
        { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
      ],
    };
    const props = {
      data_wrapper: dsWrapper(),
      summary_stats_data: [],
      setActiveCol: jest.fn(),
      outside_df_params: { post_processing: "noop" },
    };
    const { rerender } = render(<DFViewerInfinite {...props} df_viewer_config={cfgA} />);
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(<DFViewerInfinite {...props} df_viewer_config={cfgB} />);
    // Column reshape rebuilds the columnDefs memo but does not change the
    // outside_df_params React key, so AG-Grid stays mounted.
    expect(getSpyCalls().mountCount).toBe(1);
  });

  it("activeCol prop change does not remount AG-Grid", () => {
    const props = {
      data_wrapper: dsWrapper(),
      df_viewer_config: baseConfig,
      summary_stats_data: [],
      setActiveCol: jest.fn(),
      outside_df_params: { post_processing: "noop" },
    };
    const { rerender } = render(<DFViewerInfinite {...props} activeCol={["a", "header-a"]} />);
    expect(getSpyCalls().mountCount).toBe(1);
    rerender(<DFViewerInfinite {...props} activeCol={["b", "header-b"]} />);
    // activeCol changes flow through context, not through the React key.
    expect(getSpyCalls().mountCount).toBe(1);
  });

  it("summary_stats_data update during in-flight DataSource fetch applies pinned rows and does not abort the fetch", () => {
    // Mid-flight: AG-Grid has called getRows but no response yet. Then Python
    // pushes a fresh summary. The pinned-row imperative path should fire
    // independently of the data fetch.
    const getRows = jest.fn();
    const wrapper = {
      data_type: "DataSource" as const,
      length: 50,
      datasource: { rowCount: 50, getRows },
    };
    const baseProps = {
      data_wrapper: wrapper,
      df_viewer_config: baseConfig,
      setActiveCol: jest.fn(),
      outside_df_params: { post_processing: "noop" },
    };
    const { rerender } = render(
      <DFViewerInfinite {...baseProps} summary_stats_data={[{ index: "mean", a: 1 }]} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    const getRowsCallsBefore = getSpyCalls().getRowsCallArgs.length;

    rerender(
      <DFViewerInfinite {...baseProps} summary_stats_data={[{ index: "mean", a: 99 }]} />,
    );
    // pinned rows applied imperatively via setGridOption
    const pinnedCalls = getSpyCalls().setGridOption.filter(([k]) => k === "pinnedTopRowData");
    const last = pinnedCalls[pinnedCalls.length - 1][1] as Array<{ a: number }>;
    expect(last[0].a).toBe(99);
    // no remount, and no spurious additional getRows
    expect(getSpyCalls().mountCount).toBe(1);
    expect(getSpyCalls().getRowsCallArgs.length).toBe(getRowsCallsBefore);
  });

  it("error_info renders without touching the grid", () => {
    const { getByText } = render(
      <DFViewerInfinite
        data_wrapper={rawWrapper([{ index: 0, a: 1 }])}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        error_info="Boom"
      />,
    );
    expect(getByText("Boom")).toBeInTheDocument();
    expect(getSpyCalls().mountCount).toBe(1);
  });
});
