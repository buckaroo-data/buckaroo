/**
 * Flash matrix — integration layer (BuckarooInfiniteWidget).
 *
 * Pins down the cascade from buckaroo_state -> mainDs -> data_wrapper ->
 * DFViewerInfinite -> AG-Grid. Companion to DFViewerInfinite.flash.test.tsx.
 *
 * Tests assert CURRENT behavior on main (Option A in docs/rerender-test-plan.md).
 * Tests tagged "[captures current flash]" are tracking pain, not validating it.
 */
import { render } from "@testing-library/react";
import { BuckarooInfiniteWidget } from "./BuckarooWidgetInfinite";
import { KeyAwareSmartRowCache } from "./DFViewerParts/SmartRowCache";
import { getSpyCalls, resetSpy } from "../test-utils/agGridSpy";
import { BuckarooState, BuckarooOptions, DFMeta } from "./WidgetTypes";
import { DFViewerConfig } from "./DFViewerParts/DFWhole";
import { IDisplayArgs } from "./DFViewerParts/gridUtils";

jest.mock("ag-grid-react", () =>
  require("../test-utils/agGridSpy").agGridReactMockFactory(),
);
jest.mock("./useColorScheme", () => ({ useColorScheme: () => "light" }));

// StatusBar also instantiates AgGridReact; stub it so the spy only counts the data grid.
jest.mock("./StatusBar", () => ({
  StatusBar: () => <div data-testid="status-bar-stub" />,
}));

// DFViewerInfinite-prop capture for identity-stability assertion.
let dfvCalls: Array<{ outside_df_params: any; data_wrapper: any }> = [];
jest.mock("./DFViewerParts/DFViewerInfinite", () => {
  const actual = jest.requireActual("./DFViewerParts/DFViewerInfinite");
  return {
    ...actual,
    DFViewerInfinite: (props: any) => {
      dfvCalls.push({
        outside_df_params: props.outside_df_params,
        data_wrapper: props.data_wrapper,
      });
      return actual.DFViewerInfinite(props);
    },
  };
});

const baseConfig: DFViewerConfig = {
  pinned_rows: [],
  left_col_configs: [],
  column_config: [
    { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
    { col_name: "a", header_name: "a", displayer_args: { displayer: "obj" } },
  ],
};

const baseDfMeta: DFMeta = {
  total_rows: 50,
  columns: 2,
  filtered_rows: 50,
  rows_shown: 50,
};

const baseOptions: BuckarooOptions = {
  sampled: [],
  cleaning_method: ["", "clean1", "clean2"],
  post_processing: ["", "log_scale"],
  df_display: ["main", "summary"],
  show_commands: [],
};

const baseDisplayArgs: Record<string, IDisplayArgs> = {
  main: {
    data_key: "main",
    df_viewer_config: baseConfig,
    summary_stats_key: "summary_stats",
  },
  summary: {
    data_key: "summary_stats",
    df_viewer_config: baseConfig,
    summary_stats_key: "summary_stats",
  },
};

const initialState: BuckarooState = {
  sampled: false,
  cleaning_method: false,
  quick_command_args: {},
  post_processing: false,
  df_display: "main",
  show_commands: false,
};

const mkSrc = () => new KeyAwareSmartRowCache(() => {});

beforeEach(() => {
  resetSpy();
  dfvCalls = [];
});

describe("BuckarooInfiniteWidget — flash matrix (current behavior)", () => {
  it("post_processing change purges the infinite cache without remounting", () => {
    const src = mkSrc();
    const { rerender } = render(
      <BuckarooInfiniteWidget
        df_data_dict={{ summary_stats: [] }}
        df_display_args={baseDisplayArgs}
        df_meta={baseDfMeta}
        operations={[]}
        on_operations={jest.fn()}
        operation_results={{} as any}
        command_config={{ argspecs: {}, defaultArgs: {} }}
        buckaroo_state={{ ...initialState, post_processing: "" }}
        on_buckaroo_state={jest.fn()}
        buckaroo_options={baseOptions}
        src={src}
      />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    const purgesBefore = getSpyCalls().purgeInfiniteCache;

    rerender(
      <BuckarooInfiniteWidget
        df_data_dict={{ summary_stats: [] }}
        df_display_args={baseDisplayArgs}
        df_meta={baseDfMeta}
        operations={[]}
        on_operations={jest.fn()}
        operation_results={{} as any}
        command_config={{ argspecs: {}, defaultArgs: {} }}
        buckaroo_state={{ ...initialState, post_processing: "log_scale" }}
        on_buckaroo_state={jest.fn()}
        buckaroo_options={baseOptions}
        src={src}
      />,
    );
    // The React key on AgGridReact is now data_type, not the stringified
    // outside_df_params. A within-data_type content change (post_processing
    // on a main DataSource here) drives the purge-cache effect instead of a
    // full remount — that's the step-3 flash fix.
    expect(getSpyCalls().mountCount).toBe(1);
    expect(getSpyCalls().purgeInfiniteCache).toBeGreaterThan(purgesBefore);
  });

  it("cleaning_method change does NOT remount but rebuilds datasource (getRows refires)", () => {
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
    };
    const { rerender } = render(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, cleaning_method: "clean1" }} />,
    );
    const beforeMount = getSpyCalls().mountCount;
    const beforeGetRows = getSpyCalls().getRowsCallArgs.length;

    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, cleaning_method: "clean2" }} />,
    );
    // cleaning_method is in mainDs deps but NOT in outside_df_params, so:
    //   - no remount (React key unchanged)
    //   - new mainDs reference → new datasource prop → spy fires getRows again
    expect(getSpyCalls().mountCount).toBe(beforeMount);
    expect(getSpyCalls().getRowsCallArgs.length).toBeGreaterThan(beforeGetRows);
  });

  it("show_commands toggle does not remount and does not refetch", () => {
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
    };
    const { rerender } = render(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, show_commands: false }} />,
    );
    const beforeGetRows = getSpyCalls().getRowsCallArgs.length;

    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, show_commands: "1" }} />,
    );
    // show_commands is NOT in mainDs deps. The data_wrapper useMemo does
    // recompute (its deps include the whole buckaroo_state object), but the
    // datasource it ultimately exposes is reference-equal — so AG-Grid's
    // datasource prop doesn't change identity and getRows doesn't refire.
    expect(getSpyCalls().mountCount).toBe(1);
    expect(getSpyCalls().getRowsCallArgs.length).toBe(beforeGetRows);
  });

  it("outsideDFParams identity is preserved across renders when its deps are unchanged", () => {
    // useMemo with deps [operations, post_processing, quick_command_args, df_display]
    // means: when those four deps are reference-equal across renders, the array
    // returned to DFViewerInfinite is reference-equal too. That stops the React
    // `key` on AG-Grid from changing identity from spurious re-renders.
    const src = mkSrc();
    const stableOps: any[] = []; // reuse same reference across both renders
    const widgetEl = (state: BuckarooState) => (
      <BuckarooInfiniteWidget
        df_data_dict={{ summary_stats: [] }}
        df_display_args={baseDisplayArgs}
        df_meta={baseDfMeta}
        operations={stableOps}
        on_operations={jest.fn()}
        operation_results={{} as any}
        command_config={{ argspecs: {}, defaultArgs: {} }}
        buckaroo_state={state}
        on_buckaroo_state={jest.fn()}
        buckaroo_options={baseOptions}
        src={src}
      />
    );
    const { rerender } = render(widgetEl({ ...initialState, post_processing: "" }));
    const firstRef = dfvCalls[0].outside_df_params;
    expect(Array.isArray(firstRef)).toBe(true);

    // Re-render with a fresh state object whose fields are reference-equal:
    // quick_command_args is inherited from initialState ({} singleton),
    // post_processing/df_display are primitives, operations is stableOps.
    rerender(widgetEl({ ...initialState, post_processing: "" }));
    const secondRef = dfvCalls[dfvCalls.length - 1].outside_df_params;
    expect(secondRef).toBe(firstRef);
  });

  it("activeCol prop survives a post_processing change (no remount, so AG-Grid selection is preserved too)", () => {
    // Pre step 3 this was a "survives a remount" test — post_processing forced
    // a key-driven remount and activeCol survived via context. Post step 3,
    // post_processing no longer triggers a remount, so AG-Grid's internal cell
    // selection state is *also* preserved (which is exactly the flash fix we
    // wanted). This test now just confirms the prop continues to flow through.
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
    };
    render(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, post_processing: "" }} />,
    );
    // initial activeCol is ["a", "stoptime"] per BuckarooInfiniteWidget useState
    const activeColAtFirstMount = getSpyCalls().lastProps?.context?.activeCol;
    expect(activeColAtFirstMount).toEqual(["a", "stoptime"]);

    const { rerender } = render(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, post_processing: "" }} />,
    );
    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, post_processing: "log_scale" }} />,
    );
    expect(getSpyCalls().lastProps?.context?.activeCol).toEqual(["a", "stoptime"]);
  });

  it("df_display switch (main → summary) remounts the grid because data_type changes", () => {
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [{ index: "mean", a: 10 }] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
    };
    const { rerender } = render(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "main" }} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "summary" }} />,
    );
    // df_display: "main" → "summary" switches data_wrapper.data_type from
    // DataSource to Raw, which means AG-Grid's rowModelType has to change.
    // rowModelType can't be reconfigured live, so the React key on AgGridReact
    // is keyed on data_type and this *intentionally* remounts. (Plain
    // within-data_type changes like post_processing no longer remount — see
    // the prior test.)
    expect(getSpyCalls().mountCount).toBe(2);
  });

  it("dataframe_id change forces a full remount (opt-in SPA reset)", () => {
    // dataframe_id is the explicit "different dataframe" signal. Routine
    // post_processing / sort / filter changes leave it alone and benefit from
    // step-3/4's in-place update path. A change here is the rare "user opened
    // a different file" event: DFViewerInfinite remounts so AG-Grid drops its
    // selection / scroll / filter state, and dataframe_id participates in
    // outside_df_params so SmartRowCache routes to a fresh sourceName.
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
      buckaroo_state: { ...initialState, post_processing: "" },
    };
    const { rerender } = render(<BuckarooInfiniteWidget {...propsA} dataframe_id="df-1" />);
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(<BuckarooInfiniteWidget {...propsA} dataframe_id="df-2" />);
    expect(getSpyCalls().mountCount).toBe(2);
  });

  it("dataframe_id stable across post_processing change → step-3/4 in-place update path still wins", () => {
    // Verify that adopting dataframe_id doesn't accidentally turn every state
    // change into a remount. A dataframe_id that stays constant across a
    // post_processing toggle leaves the grid mounted; the step-3 purge effect
    // and step-4 stable rowIds do their job.
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
      dataframe_id: "stable",
    };
    const { rerender } = render(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, post_processing: "" }} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, post_processing: "log_scale" }} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
  });
});
