import { render } from "@testing-library/react";
import { DFViewerInfinite } from "./DFViewerInfinite";
import { DFViewerConfig } from "./DFWhole";

const setGridOptionMock = jest.fn();
let latestAgGridProps: any = null;
let agGridRenderHistory: any[] = [];
let agGridMountCount = 0;
let agGridUnmountCount = 0;

jest.mock("@ag-grid-community/react", () => {
  const React = require("react");
  return {
    AgGridReact: React.forwardRef((props: any, ref: any) => {
      latestAgGridProps = props;
      agGridRenderHistory.push(props);
      React.useImperativeHandle(ref, () => ({
        api: {
          setGridOption: setGridOptionMock,
        },
      }));
      React.useEffect(() => {
        agGridMountCount += 1;
        return () => {
          agGridUnmountCount += 1;
        };
      }, []);

      React.useEffect(() => {
        props.onGridReady?.({
          api: {
            setGridOption: setGridOptionMock,
          },
        });
      }, [props]);

      return <div data-testid="ag-grid-react-mock" />;
    }),
  };
});

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
  component_config: { className: "my-custom-theme" },
};

const renderLegacy = (ui: any) => render(ui, { legacyRoot: true });

describe("DFViewerInfinite", () => {
  beforeEach(() => {
    setGridOptionMock.mockClear();
    latestAgGridProps = null;
    agGridRenderHistory = [];
    agGridMountCount = 0;
    agGridUnmountCount = 0;
  });

  it("renders error_info and custom class name", () => {
    const { getByText, container } = renderLegacy(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        error_info="Boom"
      />,
    );

    expect(getByText("Boom")).toBeInTheDocument();
    expect(container.querySelector(".my-custom-theme")).toBeInTheDocument();
  });

  it("uses rowData for Raw mode and updates rowData via grid api on data change", () => {
    const { rerender } = renderLegacy(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
      />,
    );

    expect(latestAgGridProps.gridOptions.rowModelType).toBe("clientSide");
    expect(latestAgGridProps.gridOptions.rowData).toEqual([{ index: 0, a: 1 }]);

    rerender(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 9 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
      />,
    );

    expect(setGridOptionMock).toHaveBeenCalledWith("rowData", [{ index: 0, a: 9 }]);
  });

  it("applies pinned top rows on grid ready and summary updates", () => {
    const { rerender } = renderLegacy(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={[{ index: "mean", a: 10 }]}
        setActiveCol={jest.fn()}
      />,
    );

    expect(setGridOptionMock).toHaveBeenCalledWith("pinnedTopRowData", [{ index: "mean", a: 10 }]);

    rerender(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={[{ index: "mean", a: 22 }]}
        setActiveCol={jest.fn()}
      />,
    );

    expect(setGridOptionMock).toHaveBeenCalledWith("pinnedTopRowData", [{ index: "mean", a: 22 }]);
  });

  it("switches to infinite row model for DataSource mode", () => {
    renderLegacy(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
      />,
    );

    expect(latestAgGridProps.gridOptions.rowModelType).toBe("infinite");
    expect(latestAgGridProps.datasource.rowCount).toBe(50);
  });

  it("remounts grid and refreshes context when outside_df_params changes", () => {
    const { rerender } = renderLegacy(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ key: "A" }}
      />,
    );

    expect(agGridMountCount).toBe(1);
    expect(agGridUnmountCount).toBe(0);
    expect(latestAgGridProps.context.outside_df_params).toEqual({ key: "A" });

    rerender(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ key: "B" }}
      />,
    );

    expect(agGridMountCount).toBe(2);
    expect(agGridUnmountCount).toBe(1);
    expect(latestAgGridProps.context.outside_df_params).toEqual({ key: "B" });
    expect(
      agGridRenderHistory.some(
        (p) => JSON.stringify(p?.context?.outside_df_params) === JSON.stringify({ key: "A" }),
      ),
    ).toBe(true);
  });

  it("changes getRowId identity across outside_df_params changes", () => {
    const { rerender } = renderLegacy(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ key: "A" }}
      />,
    );

    const getRowIdA = latestAgGridProps.gridOptions.getRowId;
    const idA = getRowIdA({
      data: { index: 7 },
      context: latestAgGridProps.context,
    } as any);

    rerender(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ key: "B" }}
      />,
    );

    const getRowIdB = latestAgGridProps.gridOptions.getRowId;
    const idB = getRowIdB({
      data: { index: 7 },
      context: latestAgGridProps.context,
    } as any);

    expect(idA).not.toEqual(idB);
    expect(idA).toContain('"key":"A"');
    expect(idB).toContain('"key":"B"');
  });

  it("keeps infinite grid options and sort reset behavior after outside param changes", () => {
    const { rerender } = renderLegacy(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ key: "A" }}
      />,
    );

    expect(latestAgGridProps.gridOptions.rowModelType).toBe("infinite");
    expect(latestAgGridProps.gridOptions.maxConcurrentDatasourceRequests).toBe(3);
    expect(latestAgGridProps.gridOptions.rowBuffer).toBe(20);
    expect(latestAgGridProps.gridOptions.maxBlocksInCache).toBe(0);
    expect(latestAgGridProps.gridOptions.cacheOverflowSize).toBe(0);

    const ensureIndexVisibleA = jest.fn();
    latestAgGridProps.gridOptions.onSortChanged?.({
      api: {
        ensureIndexVisible: ensureIndexVisibleA,
        getFirstDisplayedRowIndex: jest.fn(() => 1),
        getLastDisplayedRowIndex: jest.fn(() => 20),
      },
    } as any);
    expect(ensureIndexVisibleA).toHaveBeenCalledWith(0);

    rerender(
      <DFViewerInfinite
        data_wrapper={{
          data_type: "DataSource",
          length: 50,
          datasource: { rowCount: 50, getRows: jest.fn() },
        }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
        outside_df_params={{ key: "B" }}
      />,
    );

    expect(latestAgGridProps.gridOptions.rowModelType).toBe("infinite");
    expect(latestAgGridProps.gridOptions.maxConcurrentDatasourceRequests).toBe(3);
    expect(latestAgGridProps.gridOptions.rowBuffer).toBe(20);
    expect(latestAgGridProps.gridOptions.maxBlocksInCache).toBe(0);
    expect(latestAgGridProps.gridOptions.cacheOverflowSize).toBe(0);
    expect(latestAgGridProps.datasource.rowCount).toBe(50);

    const ensureIndexVisibleB = jest.fn();
    latestAgGridProps.gridOptions.onSortChanged?.({
      api: {
        ensureIndexVisible: ensureIndexVisibleB,
        getFirstDisplayedRowIndex: jest.fn(() => 2),
        getLastDisplayedRowIndex: jest.fn(() => 30),
      },
    } as any);
    expect(ensureIndexVisibleB).toHaveBeenCalledWith(0);
  });
});
