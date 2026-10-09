import { render } from "@testing-library/react";
import { DFViewerInfinite } from "./DFViewerInfinite";
import { DFViewerConfig } from "./DFWhole";

const setGridOptionMock = jest.fn();
let latestAgGridProps: any = null;

jest.mock("ag-grid-react", () => {
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

  it("pins multiple stat rows when config requests them", () => {
    const multiPinConfig: DFViewerConfig = {
      pinned_rows: [
        { primary_key_val: "mean", displayer_args: { displayer: "obj" } },
        { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
      ],
      left_col_configs: [],
      column_config: [
        { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
        { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
        { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
      ],
      component_config: {},
    };
    const statsData = [
      { index: "mean", a: 42.5, b: 10.1 },
      { index: "dtype", a: "float64", b: "int64" },
      { index: "histogram_bins", a: [0, 25, 50, 75, 100], b: [0, 5, 10] },
    ];

    render(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1, b: 2 }], length: 1 }}
        df_viewer_config={multiPinConfig}
        summary_stats_data={statsData}
        setActiveCol={jest.fn()}
      />,
    );

    expect(setGridOptionMock).toHaveBeenCalledWith("pinnedTopRowData", [
      { index: "mean", a: 42.5, b: 10.1 },
      { index: "dtype", a: "float64", b: "int64" },
    ]);
  });

  it("passes histogram_stats in context for color mapping", () => {
    const statsData = [
      { index: "histogram_bins", a: [0, 25, 50, 75, 100] },
      { index: "histogram_log_bins", a: [1, 10, 100] },
      { index: "mean", a: 50 },
    ];

    render(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={statsData}
        setActiveCol={jest.fn()}
      />,
    );

    // The context passed to AG-Grid should include histogram_stats
    const context = latestAgGridProps.context;
    expect(context.histogram_stats).toBeDefined();
    expect(context.histogram_stats.a).toEqual({
      histogram_bins: [0, 25, 50, 75, 100],
      histogram_log_bins: [1, 10, 100],
    });
  });

  it("handles empty summary stats gracefully", () => {
    render(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={[]}
        setActiveCol={jest.fn()}
      />,
    );

    // Should not crash, pinned rows should be empty
    expect(setGridOptionMock).toHaveBeenCalledWith("pinnedTopRowData", [undefined]);
    // histogram_stats should be empty object
    const context = latestAgGridProps.context;
    expect(context.histogram_stats).toEqual({});
  });

  it("handles summary stats with null values in columns", () => {
    const statsData = [
      { index: "mean", a: 42.5, b: null },
      { index: "dtype", a: "float64", b: "object" },
    ];

    render(
      <DFViewerInfinite
        data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1, b: "x" }], length: 1 }}
        df_viewer_config={baseConfig}
        summary_stats_data={statsData}
        setActiveCol={jest.fn()}
      />,
    );

    expect(setGridOptionMock).toHaveBeenCalledWith("pinnedTopRowData", [
      { index: "mean", a: 42.5, b: null },
    ]);
  });
});
