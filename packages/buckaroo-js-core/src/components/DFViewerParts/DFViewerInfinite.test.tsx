import { render } from "@testing-library/react";
import { DFViewerInfinite } from "./DFViewerInfinite";
import { DFViewerConfig } from "./DFWhole";

const setGridOptionMock = jest.fn();
let latestAgGridProps: any = null;

jest.mock("@ag-grid-community/react", () => {
  const React = require("react");
  return {
    AgGridReact: React.forwardRef((props: any, ref: any) => {
      latestAgGridProps = props;
      React.useImperativeHandle(ref, () => ({
        api: {
          setGridOption: setGridOptionMock,
        },
      }));

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

describe("DFViewerInfinite", () => {
  beforeEach(() => {
    setGridOptionMock.mockClear();
    latestAgGridProps = null;
  });

  it("renders error_info and custom class name", () => {
    const { getByText, container } = render(
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
    const { rerender } = render(
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
    const { rerender } = render(
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
    render(
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

  it("B1: outside_df_params change causes remount (onGridReady re-fires)", () => {
    const { rerender } = render(
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

    const callsAfterMount = setGridOptionMock.mock.calls.filter(
      (c: any[]) => c[0] === "pinnedTopRowData"
    ).length;
    expect(callsAfterMount).toBeGreaterThanOrEqual(1);

    setGridOptionMock.mockClear();

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

    const pinnedCalls = setGridOptionMock.mock.calls.filter(
      (c: any[]) => c[0] === "pinnedTopRowData"
    );
    expect(pinnedCalls.length).toBeGreaterThanOrEqual(1);
    expect(latestAgGridProps.context.outside_df_params).toEqual({ key: "B" });
  });

  it("B2: getRowId output changes with outside_df_params", () => {
    const { rerender } = render(
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

    const getRowId1 = latestAgGridProps.gridOptions.getRowId;
    const id1 = getRowId1({ data: { index: 5 }, context: { outside_df_params: { key: "A" } } });
    expect(id1).toBe('5-{"key":"A"}');

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

    const getRowId2 = latestAgGridProps.gridOptions.getRowId;
    const id2 = getRowId2({ data: { index: 5 }, context: { outside_df_params: { key: "B" } } });
    expect(id2).toBe('5-{"key":"B"}');
    expect(id1).not.toBe(id2);
  });

  it("B3: DataSource mode preserves infinite options after param change", () => {
    const { rerender } = render(
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
  });

  it("B4: sort-change handler calls ensureIndexVisible(0)", () => {
    render(
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

    const onSortChanged = latestAgGridProps.gridOptions.onSortChanged;
    expect(onSortChanged).toBeDefined();

    const mockEnsureIndexVisible = jest.fn();
    onSortChanged({
      api: {
        getFirstDisplayedRowIndex: () => 5,
        getLastDisplayedRowIndex: () => 15,
        ensureIndexVisible: mockEnsureIndexVisible,
      },
    });

    expect(mockEnsureIndexVisible).toHaveBeenCalledWith(0);
  });
});
