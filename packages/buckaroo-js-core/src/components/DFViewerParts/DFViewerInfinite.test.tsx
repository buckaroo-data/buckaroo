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
});

describe("DFViewerInfinite host sort (#984)", () => {
  // Laid out like tallyman's diff frame: `b` holds the before value and is
  // hidden, `c` is the after value shown under the header "fare". The
  // rewritten ids are positional, so a host can only name the column by
  // header.
  const diffConfig: DFViewerConfig = {
    pinned_rows: [],
    left_col_configs: [{ col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } }],
    column_config: [
      { col_name: "a", header_name: "name", displayer_args: { displayer: "obj" } },
      { col_name: "b", header_name: "fare", displayer_args: { displayer: "obj" }, ag_grid_specs: { hide: true } },
      { col_name: "c", header_name: "fare", displayer_args: { displayer: "obj" } },
    ],
  };
  const dsWrapper = {
    data_type: "DataSource" as const,
    length: 50,
    datasource: { rowCount: 50, getRows: jest.fn() },
  };
  const initialSortOf = (field: string) =>
    latestAgGridProps.columnDefs.find((c: any) => c.field === field)?.initialSort;
  const fireSortChanged = (columnState: any[]) => {
    const ensureIndexVisible = jest.fn();
    latestAgGridProps.gridOptions.onSortChanged({
      api: { getColumnState: () => columnState, ensureIndexVisible },
    });
    return ensureIndexVisible;
  };

  let warnSpy: jest.SpyInstance;
  beforeEach(() => {
    latestAgGridProps = null;
    warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("initial_sort resolves a header name to the visible column; a hidden column with the same header never matches", () => {
    render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "fare", direction: "desc" }}
      />,
    );
    expect(initialSortOf("c")).toBe("desc");
    expect(initialSortOf("b")).toBeUndefined();
    expect(initialSortOf("a")).toBeUndefined();
  });

  it("ignores an initial_sort naming a column the frame doesn't have", () => {
    render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "age", direction: "asc" }}
      />,
    );
    expect(latestAgGridProps.columnDefs.some((c: any) => c.initialSort !== undefined)).toBe(false);
  });

  it("warns once per mount, naming the column, when initial_sort matches no visible header", () => {
    const onSortChange = jest.fn();
    const { rerender } = render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "age", direction: "asc" }}
        on_sort_change={onSortChange}
      />,
    );
    // a new df_viewer_config rebuilds the column defs; that's a re-render, not a new mount
    rerender(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={{ ...diffConfig }}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "age", direction: "asc" }}
        on_sort_change={onSortChange}
      />,
    );
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(String(warnSpy.mock.calls[0][0])).toContain("age");
    expect(onSortChange).not.toHaveBeenCalled();
  });

  it("doesn't warn for a known initial_sort column, or when there's no initial_sort", () => {
    const { unmount } = render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "fare", direction: "desc" }}
      />,
    );
    unmount();
    render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
      />,
    );
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("reads initial_sort once; a later change doesn't touch the column defs", () => {
    const { rerender } = render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "fare", direction: "desc" }}
      />,
    );
    rerender(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        initial_sort={{ column: "name", direction: "asc" }}
      />,
    );
    expect(initialSortOf("c")).toBe("desc");
    expect(initialSortOf("a")).toBeUndefined();
  });

  it("reports a sort change by header name, and still scrolls back to the top", () => {
    const onSortChange = jest.fn();
    render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        on_sort_change={onSortChange}
      />,
    );
    const ensureIndexVisible = fireSortChanged([
      { colId: "a", sort: null },
      { colId: "c", sort: "asc", sortIndex: 0 },
    ]);
    expect(onSortChange).toHaveBeenLastCalledWith({ column: "fare", direction: "asc" });
    expect(ensureIndexVisible).toHaveBeenCalledWith(0);
  });

  it("reports null when the sort is cleared or spans more than one column", () => {
    const onSortChange = jest.fn();
    render(
      <DFViewerInfinite
        data_wrapper={dsWrapper}
        df_viewer_config={diffConfig}
        setActiveCol={jest.fn()}
        on_sort_change={onSortChange}
      />,
    );
    fireSortChanged([{ colId: "a", sort: null }, { colId: "c", sort: null }]);
    expect(onSortChange).toHaveBeenLastCalledWith(null);

    fireSortChanged([
      { colId: "a", sort: "asc", sortIndex: 0 },
      { colId: "c", sort: "desc", sortIndex: 1 },
    ]);
    expect(onSortChange).toHaveBeenLastCalledWith(null);
    expect(onSortChange).toHaveBeenCalledTimes(2);
  });
});
