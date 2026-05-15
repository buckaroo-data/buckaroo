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
import { getSpyCalls, resetSpy, setMockColumnState } from "../test-utils/agGridSpy";
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
  it("post_processing change auto-bumps effectiveDataframeId and remounts the grid", () => {
    // post_processing changes the underlying row contents. With
    // getRowId=String(index) (step 4), in-place updates would silently match
    // the wrong record. The widget bundles post_processing into an internal
    // effective dataframe id alongside the user-supplied dataframe_id, so any
    // such change forces a full remount (correct, but visibly flashes).
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
    expect(getSpyCalls().mountCount).toBe(2);
  });

  it("cleaning_method change auto-bumps effectiveDataframeId and remounts the grid", () => {
    // cleaning_method also legitimately alters row contents (and may reorder
    // rows). Same correctness story as post_processing: full remount.
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
    expect(getSpyCalls().mountCount).toBe(1);

    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, cleaning_method: "clean2" }} />,
    );
    expect(getSpyCalls().mountCount).toBe(2);
  });

  it("quick_command_args.search change does NOT remount — purges the infinite cache instead", () => {
    // Search (and other quick_command_args entries that act as filters/sorts) is
    // a within-data_type content change. The post-#729/#730/#731 in-place update
    // path handles this correctly: outside_df_params changes → SmartRowCache
    // routes to a fresh sourceName → the purge effect calls
    // gridApi.purgeInfiniteCache() → AG-Grid asks for fresh rows via getRows,
    // which return the filtered data. Row DOM is reused (getRowId is stable
    // within a data_key) and cells update in place.
    //
    // The earlier-merged auto-bump fix (in #726) bundled quick_command_args
    // into effectiveDataframeId on a precautionary basis and reintroduced the
    // flash for every search keystroke. This test asserts the desired
    // behavior: search must look like the df_display swap from #739 — grid
    // stays mounted, datasource refetches.
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
      <BuckarooInfiniteWidget
        {...propsA}
        buckaroo_state={{ ...initialState, quick_command_args: {} }}
      />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    const purgesBefore = getSpyCalls().purgeInfiniteCache;

    rerender(
      <BuckarooInfiniteWidget
        {...propsA}
        buckaroo_state={{
          ...initialState,
          quick_command_args: { search: ["mount vernon"] },
        }}
      />,
    );

    expect(getSpyCalls().mountCount).toBe(1);
    expect(getSpyCalls().purgeInfiniteCache).toBeGreaterThan(purgesBefore);
  });

  it("operations entry marked meta.quick_command does NOT remount — Python's normalized search arrives as an op", () => {
    // The widget excludes ops with meta.quick_command=true from
    // effectiveDataframeId. Without this, Python normalizing a search keystroke
    // into an operations entry (`[{symbol:"search", meta:{quick_command:true}},
    // {symbol:"df"}, "col", val]`) bumps the remount key milliseconds after
    // the result already painted — visible flash.
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
    };
    const { rerender } = render(
      <BuckarooInfiniteWidget
        {...propsA}
        operations={[]}
        buckaroo_state={{ ...initialState, quick_command_args: {} }}
      />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    const purgesBefore = getSpyCalls().purgeInfiniteCache;

    const searchOp: any = [
      { symbol: "search", meta: { auto_clean: true, quick_command: true } },
      { symbol: "df" },
      "col",
      "was",
    ];
    rerender(
      <BuckarooInfiniteWidget
        {...propsA}
        operations={[searchOp]}
        buckaroo_state={{
          ...initialState,
          quick_command_args: { search: ["was"] },
        }}
      />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    expect(getSpyCalls().purgeInfiniteCache).toBeGreaterThan(purgesBefore);
  });

  it("operations entry WITHOUT meta.quick_command DOES remount (existing autobump behavior)", () => {
    // Regression guard: a regular (non-quick) op still bumps the remount key,
    // because its row content really does change.
    const src = mkSrc();
    const propsA = {
      df_data_dict: { summary_stats: [] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src,
      on_buckaroo_state: jest.fn(),
    };
    const { rerender } = render(
      <BuckarooInfiniteWidget {...propsA} operations={[]} buckaroo_state={initialState} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);

    const dropOp: any = [{ symbol: "dropcol" }, { symbol: "df" }, "col"];
    rerender(
      <BuckarooInfiniteWidget {...propsA} operations={[dropOp]} buckaroo_state={initialState} />,
    );
    expect(getSpyCalls().mountCount).toBe(2);
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

  it("activeCol prop survives a post_processing change via React state above the auto-bump remount", () => {
    // post_processing auto-bumps effectiveDataframeId and remounts the grid
    // (AG-Grid drops its internal selection). But activeCol lives in
    // BuckarooInfiniteWidget's useState — above the remount boundary — so the
    // app-level "currently focused column" survives and flows back through
    // context to the freshly mounted grid.
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

  it("df_display switch (main ↔ summary) keeps the grid mounted — headers stay across the swap", () => {
    // Pre-this-PR: summary stats came through as data_type="Raw", which flipped
    // AG-Grid's rowModelType and forced a remount on every main↔summary toggle.
    // Now summary stats are wrapped in a fake static IDatasource so both
    // sides of the swap are data_type="DataSource". The React key on
    // AgGridReact is keyed on data_type, so it doesn't change → no remount.
    // Column headers, theme, options stay mounted; only datasource swaps and
    // rows re-fetch from the new (fake) DS.
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
    expect(getSpyCalls().mountCount).toBe(1);

    // And back to main: still no remount.
    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "main" }} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
  });

  it("dataframe_id change forces a full remount (explicit SPA reset)", () => {
    // dataframe_id is the explicit "different dataframe" signal used by SPA
    // embedders (e.g. route change → different dataset). DFViewerInfinite
    // remounts so AG-Grid drops its selection / scroll / filter state, and
    // dataframe_id participates in outside_df_params so SmartRowCache routes
    // to a fresh sourceName. The widget *also* auto-bumps an internal
    // effective dataframe id on row-content-changing state, but the explicit
    // prop is the canonical signal for the SPA-reset use case.
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

  it("stable dataframe_id does NOT save us from a post_processing change — auto-bump still fires", () => {
    // The earlier draft of this PR tried to keep the in-place update path for
    // post_processing as long as dataframe_id didn't change. That broke
    // correctness: getRowId=String(index) silently matches different records
    // pre- vs post-transform. The naive fix is to remount on row-content
    // changes regardless of dataframe_id stability.
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
    expect(getSpyCalls().mountCount).toBe(2);
  });

  it("UI-only state (show_commands) still uses the in-place update path even with the auto-bump in place", () => {
    // Sanity check: the auto-bump must be narrow. Toggling UI state that
    // doesn't change row contents (here: show_commands) must NOT bump
    // effectiveDataframeId — otherwise opening the lowcode panel would flash
    // the grid every time.
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
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, show_commands: false }} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
    rerender(
      <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, show_commands: "1" }} />,
    );
    expect(getSpyCalls().mountCount).toBe(1);
  });

  describe("per-view column state save/restore on df_display change", () => {
    const propsBase = () => ({
      df_data_dict: { summary_stats: [{ index: "mean", a: 10 }] },
      df_display_args: baseDisplayArgs,
      df_meta: baseDfMeta,
      operations: [],
      on_operations: jest.fn(),
      operation_results: {} as any,
      command_config: { argspecs: {}, defaultArgs: {} },
      buckaroo_options: baseOptions,
      src: mkSrc(),
      on_buckaroo_state: jest.fn(),
    });

    it("first entry to summary applies defaultState: { sort: null } (no carried-over sort)", () => {
      const propsA = propsBase();
      const { rerender } = render(
        <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "main" }} />,
      );
      const applyBefore = getSpyCalls().applyColumnState.length;

      rerender(
        <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "summary" }} />,
      );

      const applyAfter = getSpyCalls().applyColumnState.slice(applyBefore);
      // At least one applyColumnState fired on the swap. The most-recent call
      // should be the "no sort" default since we've never been to summary
      // before in this component instance.
      expect(applyAfter.length).toBeGreaterThanOrEqual(1);
      const last = applyAfter[applyAfter.length - 1];
      expect(last.defaultState).toEqual({ sort: null });
    });

    it("returning to a previously-visited view applies its saved column state", () => {
      const propsA = propsBase();
      // Seed the spy with a "current column state" the widget will see when
      // it reads via getColumnState() on swap-away. Simulates the user having
      // sorted column "a" descending while on main.
      const mainSavedState = [{ colId: "a", sort: "desc", sortIndex: 0 }];
      setMockColumnState(mainSavedState);

      const { rerender } = render(
        <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "main" }} />,
      );

      // Swap to summary — widget reads main's state from gridApi (returns
      // mainSavedState) and stashes it; then applies "no sort" default for summary.
      rerender(
        <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "summary" }} />,
      );

      // While on summary, change the mock state to something else — simulates
      // user having no sort on summary.
      setMockColumnState([]);
      const applyCallsBeforeReturn = getSpyCalls().applyColumnState.length;

      // Swap back to main — widget should apply the stashed mainSavedState.
      rerender(
        <BuckarooInfiniteWidget {...propsA} buckaroo_state={{ ...initialState, df_display: "main" }} />,
      );

      const applyCallsOnReturn = getSpyCalls().applyColumnState.slice(applyCallsBeforeReturn);
      expect(applyCallsOnReturn.length).toBeGreaterThanOrEqual(1);
      const last = applyCallsOnReturn[applyCallsOnReturn.length - 1];
      expect(last.state).toEqual(mainSavedState);
    });
  });
});
