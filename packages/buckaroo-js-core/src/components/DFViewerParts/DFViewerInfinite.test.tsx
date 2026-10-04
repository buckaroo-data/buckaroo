import { render, waitFor } from "@testing-library/react";
import { DFViewerInfinite } from "./DFViewerInfinite";
import { DFViewerConfig } from "./DFWhole";

const setGridOptionMock = jest.fn();
let latestAgGridProps: any = null;
// The ids of the columns the mocked grid has in its viewport, rendered as the
// header cells AG Grid renders for them (jest.mock factories may read
// variables whose names start with "mock").
let mockVirtualColumnIds: string[] = [];

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

      return (
        <div data-testid="ag-grid-react-mock">
          <div className="ag-header-viewport">
            {mockVirtualColumnIds.map((id) => (
              <div key={id} className="ag-header-cell" col-id={id} />
            ))}
          </div>
        </div>
      );
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
    mockVirtualColumnIds = [];
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
});

// Rows-first c4b: the stats scheduler asks the server for the units covering
// the columns the user is looking at first, so the grid reports them.
describe("DFViewerInfinite on_visible_columns (rows-first c4b)", () => {
  const wideConfig: DFViewerConfig = {
    pinned_rows: [],
    left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } }],
    column_config: [
      { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
      { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
      { col_name: "c", header_name: "c", displayer_args: { displayer: "obj" } },
      { col_name: "d", header_name: "d", displayer_args: { displayer: "obj" } },
    ],
  };
  const viewer = (onVisible?: (columns: string[]) => void) => (
    <DFViewerInfinite
      data_wrapper={{ data_type: "Raw", data: [{ index: 0, a: 1 }], length: 1 }}
      df_viewer_config={wideConfig}
      summary_stats_data={[]}
      setActiveCol={jest.fn()}
      on_visible_columns={onVisible}
    />
  );
  // The grid renders its header cells a frame after the event that moves them.
  const aFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));

  beforeEach(() => {
    mockVirtualColumnIds = [];
  });

  it("reports the data columns in the grid's viewport once the grid is ready, not the index column", async () => {
    mockVirtualColumnIds = ["index", "a", "b"];
    const onVisible = jest.fn();
    render(viewer(onVisible));
    await waitFor(() => expect(onVisible).toHaveBeenCalledWith(["a", "b"]));
    await aFrame();
    expect(onVisible).toHaveBeenCalledTimes(1);
  });

  it("reports again when the viewport's columns change, and not when they stay the same", async () => {
    mockVirtualColumnIds = ["index", "a", "b"];
    const onVisible = jest.fn();
    const { rerender } = render(viewer(onVisible));
    await waitFor(() => expect(onVisible).toHaveBeenCalledTimes(1));
    expect(typeof latestAgGridProps.onVirtualColumnsChanged).toBe("function");

    // The same columns again, as a resize can produce.
    latestAgGridProps.onVirtualColumnsChanged({});
    await aFrame();
    expect(onVisible).toHaveBeenCalledTimes(1);

    // The user scrolls right: the grid swaps its header cells and says so.
    mockVirtualColumnIds = ["index", "c", "d"];
    rerender(viewer(onVisible));
    latestAgGridProps.onVirtualColumnsChanged({});
    await waitFor(() => expect(onVisible).toHaveBeenCalledTimes(2));
    expect(onVisible).toHaveBeenLastCalledWith(["c", "d"]);
  });

  it("reports an empty list when no data column is in the viewport (a grid that is not laid out yet)", async () => {
    mockVirtualColumnIds = ["index"];
    const onVisible = jest.fn();
    render(viewer(onVisible));
    await waitFor(() => expect(onVisible).toHaveBeenCalledWith([]));
  });
});
