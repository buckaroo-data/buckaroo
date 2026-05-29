/**
 * Height modes SPA — buckaroo-data.readthedocs.io/en/latest/height-modes/
 *
 * Standalone React app demonstrating all Buckaroo height configurations.
 * No iframes; every widget instance shares the same DOM.
 * Toggle buttons swap the active config; a scrollable panel explains it.
 */
import * as React from "react";
import * as ReactDOM from "react-dom/client";
import { DFViewerInfinite } from "../../packages/buckaroo-js-core/src/components/DFViewerParts/DFViewerInfinite";
import type { DFViewerConfig, ComponentConfig, PinnedRowConfig, DFData } from "../../packages/buckaroo-js-core/src/components/DFViewerParts/DFWhole";
import type { DatasourceOrRaw } from "../../packages/buckaroo-js-core/src/components/DFViewerParts/DFViewerDataHelper";
import type { SetColumnFunc } from "../../packages/buckaroo-js-core/src/components/DFViewerParts/gridUtils";
import "../../packages/buckaroo-js-core/dist/style.css";

// ─── static data ─────────────────────────────────────────────────────────────

const FIVE_ROWS: DFData = [
    { index: 0, name: "Alice",   value: 42.5 },
    { index: 1, name: "Bob",     value: 73.1 },
    { index: 2, name: "Charlie", value: 19.8 },
    { index: 3, name: "Diana",   value: 88.0 },
    { index: 4, name: "Eve",     value: 55.3 },
];

const FIVE_HUNDRED_ROWS: DFData = Array.from({ length: 500 }, (_, i) => ({
    index: i,
    name: `row_${String(i).padStart(3, "0")}`,
    value: parseFloat((Math.sin(i * 0.1) * 100).toFixed(2)),
}));

const STAT_KEYS = ["dtype","count","unique","mean","std","min","25%","50%","75%","max"];
const TEN_STATS: DFData = STAT_KEYS.map((k) => ({
    index: k,
    name: k === "dtype" ? "object" : "—",
    value: k === "dtype" ? "float64" : k === "count" ? 500 : "—",
}));
const TEN_PINNED: PinnedRowConfig[] = STAT_KEYS.map((k) => ({
    primary_key_val: k,
    displayer_args: { displayer: "obj" as const },
}));

// ─── config registry ──────────────────────────────────────────────────────────

interface HeightConfig {
    id: string;
    label: string;
    modeName: string;
    data: DFData;
    pinnedRows: PinnedRowConfig[];
    summaryStats: DFData;
    compConfig?: ComponentConfig;
    /** Red-border outer div height. undefined = auto (shrinks to content). */
    outerHeight?: number | string;
    /** The AG Grid domLayout that results from this config. */
    resolvedDomLayout: "autoHeight" | "normal";
    /** Multiline breakdown of how Buckaroo arrived at resolvedDomLayout. */
    decisionTrace: string;
    /** Multiline summary of what Buckaroo passed to AG Grid. */
    agGridSaw: string;
    description: string;
    whenToUse: string;
    pythonSnippet: string;
    embedSnippet: string;
}

function makeRaw(data: DFData): DatasourceOrRaw {
    return { data_type: "Raw", data, length: data.length };
}

function makeColConfig(pinnedRows: PinnedRowConfig[], compConfig?: ComponentConfig): DFViewerConfig {
    return {
        column_config: [
            { col_name: "name",  header_name: "Name",  displayer_args: { displayer: "obj" as const } },
            { col_name: "value", header_name: "Value", displayer_args: { displayer: "float" as const, min_fraction_digits: 1, max_fraction_digits: 2 } },
        ],
        pinned_rows: pinnedRows,
        left_col_configs: [
            { col_name: "index", header_name: "#", displayer_args: { displayer: "obj" as const } },
        ],
        component_config: compConfig,
    };
}

const CONFIGS: HeightConfig[] = [
    {
        id: "auto-5",
        label: "5 rows",
        modeName: "Auto-detected autoHeight  (shortMode = true)",
        data: FIVE_ROWS,
        pinnedRows: [],
        summaryStats: [],
        outerHeight: undefined,
        resolvedDomLayout: "autoHeight",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 5
  pinnedRows             = 0
  total                  = 5

  dfvHeight              = window.innerHeight / height_fraction
                         = window.innerHeight / 2   (default fraction)
  rowHeight              = 21 px  (default AG Grid row height)
  scrollSlop             = 3      (rows reserved for widget chrome)
  maxRowsWithoutScrolling = floor(dfvHeight / 21) - 3
                         ≈ 18  (at a 900 px viewport)

  5 + 0 = 5  <  18  →  shortMode = true
  →  domLayout: "autoHeight"`,
        agGridSaw:
`domLayout prop   = "autoHeight"
                   ↳ AG Grid sizes itself to its content rows.
                     No scrollbar; grid height = rows × rowHeight.

Container CSS     = { minHeight: 50px, maxHeight: ≈450px, overflow: hidden }
  (shortDivStyle — used when shortMode=true and domLayout=autoHeight)
  The maxHeight cap prevents unbounded growth for unexpectedly large
  data. The grid never reaches it here because 5 rows ≈ 135px.`,
        description:
            "Buckaroo runs a shortMode check on every render. When the total " +
            "of data rows plus pinned rows fits inside the default dfvHeight without " +
            "triggering a scrollbar, shortMode is set to true and the grid switches " +
            "to domLayout: \"autoHeight\". The grid expands to show all rows; " +
            "the outer container (red border) follows. No component_config is needed.",
        whenToUse:
            "Notebook-style stacked embeds where each cell should be exactly as tall " +
            "as its data. A 3-row aggregate and a 100-row frame both look right — no " +
            "fixed height that wastes space or clips content.",
        pythonSnippet:
`# No config needed — shortMode is detected automatically.
import buckaroo
w = buckaroo.BuckarooWidget(df)   # 5 rows → shortMode → autoHeight

# To inspect the threshold in Python:
# maxRowsWithoutScrolling ≈ floor(dfvHeight / rowHeight) - scrollSlop`,
        embedSnippet:
`// React embed: no overrides needed.
<BuckarooServerView wsUrl="ws://localhost:8700/ws/session" />

// component_config: leave empty or omit entirely
{}`,
    },
    {
        id: "auto-pinned",
        label: "5 + 10 pinned",
        modeName: "Auto-detected autoHeight  (shortMode = true, with pinned rows)",
        data: FIVE_ROWS,
        pinnedRows: TEN_PINNED,
        summaryStats: TEN_STATS,
        outerHeight: undefined,
        resolvedDomLayout: "autoHeight",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 5
  pinnedRows             = 10  ← counted in the shortMode check
  total                  = 15

  maxRowsWithoutScrolling ≈ 18  (at a 900 px viewport, same as above)

  5 + 10 = 15  <  18  →  shortMode = true
  →  domLayout: "autoHeight"

  Pinned rows are included in the threshold arithmetic.
  They appear locked at the top of the grid, above the
  scrollable data rows.`,
        agGridSaw:
`domLayout prop   = "autoHeight"
                   ↳ AG Grid sizes itself to its content rows.

Container CSS     = { minHeight: 50px, maxHeight: ≈450px, overflow: hidden }
  (shortDivStyle — shortMode=true, domLayout=autoHeight)
  15 rows × 21px ≈ 315px — well within the maxHeight cap.
  Pinned rows are part of the rendered row count AG Grid sizes to.`,
        description:
            "Pinned rows count the same as data rows in the shortMode threshold. " +
            "With 10 stat rows (dtype, count, mean…) pinned above 5 data rows, the " +
            "combined total is 15, which still fits inside the default dfvHeight. " +
            "shortMode fires, the grid auto-sizes. Pinned rows stay fixed at the " +
            "top of the grid regardless of scroll position.",
        whenToUse:
            "Buckaroo's built-in summary view automatically pins dtype/count/mean rows. " +
            "Any small table that benefits from persistent header stats. As long as " +
            "numRows + pinnedRows < maxRowsWithoutScrolling the grid stays compact.",
        pythonSnippet:
`# Pinned rows come from df_viewer_config, not the main data.
# Buckaroo wires them up automatically in summary view:
w = buckaroo.BuckarooWidget(df)  # click "summary" in the status bar

# To set them manually:
from buckaroo import BuckarooWidget
w = BuckarooWidget(df, column_config_overrides={
    "pinned_rows": [
        {"primary_key_val": "dtype",  "displayer_args": {"displayer": "obj"}},
        {"primary_key_val": "count",  "displayer_args": {"displayer": "obj"}},
    ]
})`,
        embedSnippet:
`// Pinned rows declared in df_viewer_config.
// Their data comes from df_data_dict[summary_stats_key].
const displayArgs = {
  main: {
    data_key: "main",
    df_viewer_config: {
      pinned_rows: [
        { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
        { primary_key_val: "count", displayer_args: { displayer: "obj" } },
        // ... more stat rows
      ],
    },
    summary_stats_key: "all_stats",  // key into df_data_dict
  },
};`,
    },
    {
        id: "normal-500",
        label: "500 rows",
        modeName: "Auto-detected normal mode  (shortMode = false)",
        data: FIVE_HUNDRED_ROWS,
        pinnedRows: [],
        summaryStats: [],
        outerHeight: "50vh",
        resolvedDomLayout: "normal",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 500
  pinnedRows             = 0
  total                  = 500

  maxRowsWithoutScrolling ≈ 18  (at a 900 px viewport)

  500 + 0 = 500  ≥  18  →  shortMode = false
  →  domLayout: "normal"

  dfvHeight = window.innerHeight / height_fraction
            = window.innerHeight / 2   (default fraction = 2)
            ≈ 450 px  (at a 900 px viewport)

  Outer container must be set to the same height (50vh here).`,
        agGridSaw:
`domLayout prop   = "normal"
                   ↳ AG Grid fills 100% of its parent container's height.
                     Rows that overflow get a virtual scrollbar.

Container CSS     = { height: ≈450px, overflow: hidden }
  (regularDivStyle — shortMode=false, so useShortStyle=false)
  At a 900px viewport: window.innerHeight / 2 = 450px.
  The outer container (red border) must also be 450px / 50vh.`,
        description:
            "When the row count exceeds maxRowsWithoutScrolling, shortMode is false " +
            "and the grid uses domLayout: \"normal\" — a fixed-height viewport with a " +
            "scrollbar for overflow rows. The default height is window.innerHeight / 2. " +
            "Set the outer container (red border) to the same value so it hugs the grid.",
        whenToUse:
            "Most production embeds with large datasets that need virtual scrolling. " +
            "The default half-viewport height works well for a single full-page widget; " +
            "it can feel oversized in multi-widget dashboards — adjust with height_fraction " +
            "or an explicit dfvHeight.",
        pythonSnippet:
`# Default behaviour — no config needed.
w = buckaroo.BuckarooWidget(df)   # 500 rows → shortMode=false → normal

# To change the fraction (default 2 = half viewport):
w = buckaroo.BuckarooWidget(df, component_config={"height_fraction": 3})
# height_fraction=3  →  dfvHeight = window.innerHeight / 3  ≈ 300 px`,
        embedSnippet:
`// Outer div must match dfvHeight. Default dfvHeight = window.innerHeight/2:
<div style={{ height: "50vh" }}>
  <BuckarooServerView wsUrl="ws://..." />
</div>

// Or pass an explicit component_config to lock the height:
// { "dfvHeight": 400 }  (see "Explicit 200 px" tab)`,
    },
    {
        id: "normal-500-pinned",
        label: "500 + 10 pinned",
        modeName: "Auto-detected normal mode  (shortMode = false, with pinned rows)",
        data: FIVE_HUNDRED_ROWS,
        pinnedRows: TEN_PINNED,
        summaryStats: TEN_STATS,
        outerHeight: "50vh",
        resolvedDomLayout: "normal",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 500
  pinnedRows             = 10
  total                  = 510

  maxRowsWithoutScrolling ≈ 18

  510 ≥ 18  →  shortMode = false
  →  domLayout: "normal"

  dfvHeight = window.innerHeight / 2  (default)

  Pinned rows appear at the top of the fixed-height viewport.
  The remaining vertical space is used for scrollable data rows.`,
        agGridSaw:
`domLayout prop   = "normal"
                   ↳ AG Grid fills 100% of its parent container's height.

Container CSS     = { height: ≈450px, overflow: hidden }
  (regularDivStyle — shortMode=false)
  AG Grid internally splits the height between the pinned row area and
  the scrollable data viewport. The split is automatic.`,
        description:
            "Normal mode with 10 stat rows pinned at the top of the grid. " +
            "The pinned area is not scrollable; the 500 data rows scroll independently " +
            "below it. The fixed viewport height is split between the pinned header " +
            "and the scrollable data region automatically by AG Grid.",
        whenToUse:
            "Analytical dashboards where dtype/count/mean need to stay visible while " +
            "the analyst scrolls through raw data. The pinned rows don't reduce the " +
            "number of scrollable rows — AG Grid allocates space independently.",
        pythonSnippet:
`# Pinned summary stats + large scrollable data:
w = buckaroo.BuckarooWidget(df)
# Toggle to "summary" view in the status bar to see pinned rows.
# Buckaroo wires this up automatically.`,
        embedSnippet:
`// Same pattern as the "5 + 10 pinned" tab but the dataset is large,
// so the grid stays in normal mode and the data rows scroll.
const displayArgs = {
  main: {
    data_key: "main",
    df_viewer_config: {
      pinned_rows: STAT_PINNED_CONFIG,
      component_config: {},   // no layoutType override; auto-detect runs
    },
    summary_stats_key: "all_stats",
  },
};`,
    },
    {
        id: "explicit-200",
        label: "Explicit 200 px",
        modeName: "Explicit dfvHeight: 200  (overrides default height)",
        data: FIVE_HUNDRED_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { dfvHeight: 200 },
        outerHeight: 200,
        resolvedDomLayout: "normal",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:
  numRows = 500, pinnedRows = 0, total = 500 ≥ maxRows
  →  shortMode = false  →  domLayout: "normal"

dfvHeight resolution:
  component_config.dfvHeight = 200  ← explicit value set
  (overrides the default: window.innerHeight / height_fraction)

  Grid height = 200 px exactly.
  Outer container must also be 200 px.`,
        agGridSaw:
`domLayout prop   = "normal"
                   ↳ AG Grid fills 100% of its parent container's height.

Container CSS     = { height: 200px, overflow: hidden }
  (regularDivStyle — dfvHeight explicitly 200, shortMode=false for 500 rows)
  200px is an absolute value; it does not change with the browser window.`,
        description:
            "component_config.dfvHeight sets an exact pixel height for the AG Grid " +
            "viewport, overriding the default of window.innerHeight / height_fraction. " +
            "layoutType is still auto-detected (500 rows → normal), but the viewport " +
            "height is 200 px instead of half the browser window. " +
            "Set the outer container (red border) to the same value.",
        whenToUse:
            "Fixed-height slots in a dashboard or layout system where the widget " +
            "footprint is designed upfront. Predictable across all screen sizes — " +
            "no viewport math needed. Good for embedding in a grid layout (e.g. " +
            "a 200 px card in a three-column dashboard).",
        pythonSnippet:
`w = buckaroo.BuckarooWidget(df, component_config={"dfvHeight": 200})

# Or via the /load HTTP endpoint:
requests.post("/load", json={
    "session": "my-session",
    "path":    "data.csv",
    "component_config": {"dfvHeight": 200},
})`,
        embedSnippet:
`// Outer div must match dfvHeight exactly.
<div style={{ height: 200 }}>
  <DFViewerInfiniteDS
    df_display_args={{
      main: {
        df_viewer_config: {
          component_config: { dfvHeight: 200 },
        },
        // ...
      },
    }}
    // ...
  />
</div>`,
    },
    {
        id: "explicit-200-5rows",
        label: "200px (5 rows)",
        modeName: "Explicit dfvHeight: 200 with 5 rows — shortMode still fires",
        data: FIVE_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { dfvHeight: 200 },
        outerHeight: undefined,
        resolvedDomLayout: "autoHeight",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 5
  pinnedRows             = 0
  total                  = 5

  dfvHeight              = component_config.dfvHeight = 200  ← explicit
  rowHeight              = 21 px  (default)
  scrollSlop             = 3
  maxRowsWithoutScrolling = floor(200 / 21) - 3
                         = floor(9.5) - 3
                         = 9 - 3
                         = 6

  5 + 0 = 5  <  6  →  shortMode = true
  →  domLayout: "autoHeight"

Key point: dfvHeight=200 does NOT force normal mode.
It changes the scroll threshold (fewer rows now trigger normal)
and caps the container maxHeight, but layout type is still
auto-detected from the row count.`,
        agGridSaw:
`domLayout prop   = "autoHeight"
                   ↳ AG Grid sizes itself to its content rows.

Container CSS     = { minHeight: 50px, maxHeight: 200px, overflow: hidden }
  (shortDivStyle — shortMode=true, domLayout=autoHeight)
  5 rows × 21px ≈ 105px — grid renders at ~105px, well within 200px cap.
  The outer container (red border) shrinks to match the grid.

Compare with the 200px / 500 rows tab:
  500 rows → shortMode=false → domLayout="normal" → container height=200px.
  5 rows   → shortMode=true  → domLayout="autoHeight" → grid shrinks to rows.`,
        description:
            "Setting dfvHeight does not force normal mode — it sets the scroll threshold " +
            "and the container's maxHeight cap, but the layout type is still auto-detected. " +
            "With only 5 rows and dfvHeight=200, shortMode fires (5 < 6 rows threshold) " +
            "and the grid shrinks to its content just like the plain '5 rows' example. " +
            "To force a fixed 200px height on small data, also set layoutType: \"normal\".",
        whenToUse:
            "When you want an explicit dfvHeight cap but are fine with the grid shrinking " +
            "to content on small datasets. The maxHeight prevents unbounded growth if data " +
            "unexpectedly becomes large, while still allowing compact rendering for small data.",
        pythonSnippet:
`# dfvHeight alone does not lock layout to normal mode:
w = buckaroo.BuckarooWidget(df_5rows, component_config={"dfvHeight": 200})
# → autoHeight (5 rows fit inside the 200px threshold)

# To force fixed height on small data, also set layoutType:
w = buckaroo.BuckarooWidget(df_5rows, component_config={
    "dfvHeight": 200,
    "layoutType": "normal",   # prevents shortMode from firing
})`,
        embedSnippet:
`// dfvHeight alone on small data → autoHeight still fires:
<DFViewerInfiniteDS
  df_display_args={{
    main: { df_viewer_config: { component_config: { dfvHeight: 200 } } },
  }}
  // ...
/>

// To pin to exactly 200px regardless of row count:
component_config: { dfvHeight: 200, layoutType: "normal" }`,
    },
    {
        id: "fraction-4",
        label: "¼ viewport",
        modeName: "height_fraction: 4  →  dfvHeight = window.innerHeight / 4",
        data: FIVE_HUNDRED_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { height_fraction: 4 },
        outerHeight: "25vh",
        resolvedDomLayout: "normal",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:
  numRows = 500, pinnedRows = 0, total = 500 ≥ maxRows
  →  shortMode = false  →  domLayout: "normal"

dfvHeight resolution:
  component_config.dfvHeight  not set
  component_config.height_fraction = 4
  dfvHeight = window.innerHeight / height_fraction
            = window.innerHeight / 4

  Grid height tracks the browser window. Resize the window
  and the grid adjusts on next render.
  Outer container set to "25vh" to match.`,
        agGridSaw:
`domLayout prop   = "normal"
                   ↳ AG Grid fills 100% of its parent container's height.

Container CSS     = { height: ≈225px, overflow: hidden }
  (regularDivStyle — dfvHeight = window.innerHeight / 4 ≈ 225px at 900px)
  This value changes when the browser is resized; the grid re-renders
  with a new computed height on the next interaction.`,
        description:
            "height_fraction is a viewport-relative height without hardcoding pixels. " +
            "Buckaroo computes dfvHeight = window.innerHeight / height_fraction in the " +
            "browser, so the grid scales with the user's screen. The default fraction is " +
            "2 (half the viewport). Fraction 3 ≈ 33%, fraction 4 ≈ 25%, and so on.",
        whenToUse:
            "Pages that need to stay proportional to the user's screen. Works well for " +
            "full-page data explorers and presentation decks where the grid should occupy " +
            "a consistent fraction of the screen across laptop and 4K monitors, without " +
            "requiring CSS media queries.",
        pythonSnippet:
`# height_fraction=4  →  25% of the browser viewport height
w = buckaroo.BuckarooWidget(df, component_config={"height_fraction": 4})

# Default is height_fraction=2 (50% viewport).
# Larger fraction = shorter widget:
#   height_fraction=2  →  50vh
#   height_fraction=3  →  33vh
#   height_fraction=4  →  25vh`,
        embedSnippet:
`// Outer div should use the equivalent vh fraction:
//   height_fraction=4  →  height: "25vh"
<div style={{ height: "25vh" }}>
  <DFViewerInfiniteDS
    df_display_args={{
      main: {
        df_viewer_config: {
          component_config: { height_fraction: 4 },
        },
      },
    }}
    // ...
  />
</div>`,
    },
    {
        id: "fraction-4-5rows",
        label: "¼ vp (5 rows)",
        modeName: "height_fraction: 4 with 5 rows — shortMode still fires",
        data: FIVE_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { height_fraction: 4 },
        outerHeight: undefined,
        resolvedDomLayout: "autoHeight",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 5
  pinnedRows             = 0
  total                  = 5

  dfvHeight              = window.innerHeight / height_fraction
                         = window.innerHeight / 4  ≈ 225 px  (900px viewport)
  rowHeight              = 21 px  (default)
  scrollSlop             = 3
  maxRowsWithoutScrolling = floor(225 / 21) - 3
                         = floor(10.7) - 3
                         = 10 - 3
                         = 7

  5 + 0 = 5  <  7  →  shortMode = true
  →  domLayout: "autoHeight"

height_fraction=4 makes the viewport shorter (225px vs 450px default),
which lowers the scroll threshold from ~18 to ~7 rows.
With 5 rows that still fits, so autoHeight fires.`,
        agGridSaw:
`domLayout prop   = "autoHeight"
                   ↳ AG Grid sizes itself to its content rows.

Container CSS     = { minHeight: 50px, maxHeight: ≈225px, overflow: hidden }
  (shortDivStyle — shortMode=true, domLayout=autoHeight)
  5 rows ≈ 105px — grid renders compactly within the 225px cap.
  The outer container shrinks to match the grid, not 25vh.`,
        description:
            "height_fraction controls dfvHeight but not the layout type. With a ¼-viewport " +
            "height and only 5 rows, shortMode still fires — the row count is below the " +
            "(now lower) threshold of ~7 rows, so the grid auto-sizes to content. " +
            "The maxHeight cap is ≈225px but the grid only uses ~105px.",
        whenToUse:
            "Same as ¼ viewport for large data, but demonstrates that small datasets " +
            "keep their compact rendering even when dfvHeight is set. No intervention needed.",
        pythonSnippet:
`w = buckaroo.BuckarooWidget(df_5rows, component_config={"height_fraction": 4})
# 5 rows → shortMode=true → autoHeight
# height_fraction only affects dfvHeight, not whether normal/auto fires`,
        embedSnippet:
`<DFViewerInfiniteDS
  df_display_args={{
    main: { df_viewer_config: { component_config: { height_fraction: 4 } } },
  }}
  // ...
/>
// 5 rows → autoHeight regardless of height_fraction`,
    },
    {
        id: "fraction-75vh",
        label: "¾ viewport",
        modeName: "height_fraction: 4/3  →  dfvHeight = window.innerHeight × ¾",
        data: FIVE_HUNDRED_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { height_fraction: 4/3 },
        outerHeight: "75vh",
        resolvedDomLayout: "normal",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 500
  pinnedRows             = 0
  total                  = 500

  dfvHeight              = window.innerHeight / height_fraction
                         = window.innerHeight / (4/3)
                         = window.innerHeight × 0.75
                         ≈ 675 px  (900px viewport)
  rowHeight              = 21 px  (default)
  scrollSlop             = 3
  maxRowsWithoutScrolling = floor(675 / 21) - 3
                         = floor(32.1) - 3
                         = 32 - 3
                         = 29

  500 + 0 = 500  ≥  29  →  shortMode = false
  →  domLayout: "normal"

Note: height_fraction = 4/3 gives ¾ of the viewport.
  window.innerHeight / (4/3) = window.innerHeight × (3/4) = 75vh`,
        agGridSaw:
`domLayout prop   = "normal"
                   ↳ AG Grid fills 100% of its parent container's height.

Container CSS     = { height: ≈675px, overflow: hidden }
  (regularDivStyle — shortMode=false)
  At a 900px viewport: window.innerHeight / (4/3) = 675px = 75vh.
  The outer container (red border) must also be 75vh.`,
        description:
            "height_fraction: 4/3 gives three-quarters of the viewport — useful for " +
            "large data exploration pages where you want the grid to dominate the screen " +
            "without being full-height. The fraction can be any number; it doesn't have " +
            "to be an integer. height_fraction = 4/3 ≈ 1.33.",
        whenToUse:
            "Full-screen data exploration tools or dashboards where a single table " +
            "should take most of the vertical space, leaving room for a header or toolbar. " +
            "Works well paired with a sticky header above the grid.",
        pythonSnippet:
`# height_fraction accepts any number, not just integers:
w = buckaroo.BuckarooWidget(df, component_config={"height_fraction": 4/3})
# dfvHeight = window.innerHeight / (4/3) = window.innerHeight × 0.75 = 75vh`,
        embedSnippet:
`// Outer div must match: height_fraction=4/3 → "75vh"
<div style={{ height: "75vh" }}>
  <DFViewerInfiniteDS
    df_display_args={{
      main: { df_viewer_config: { component_config: { height_fraction: 4/3 } } },
    }}
    // ...
  />
</div>`,
    },
    {
        id: "fraction-75vh-5rows",
        label: "¾ vp (5 rows)",
        modeName: "height_fraction: 4/3 with 5 rows — shortMode fires despite large dfvHeight",
        data: FIVE_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { height_fraction: 4/3 },
        outerHeight: undefined,
        resolvedDomLayout: "autoHeight",
        decisionTrace:
`layoutType not set in component_config → auto-detect runs:

  numRows                = 5
  pinnedRows             = 0
  total                  = 5

  dfvHeight              ≈ 675 px  (window.innerHeight × 0.75 at 900px)
  rowHeight              = 21 px  (default)
  scrollSlop             = 3
  maxRowsWithoutScrolling = floor(675 / 21) - 3
                         = 32 - 3
                         = 29

  5 + 0 = 5  <  29  →  shortMode = true
  →  domLayout: "autoHeight"

A larger dfvHeight raises the scroll threshold (29 rows vs ~18 default).
With 5 rows this still fits, so the grid still auto-sizes to content.
The large maxHeight cap (675px) is never reached by 5 rows.`,
        agGridSaw:
`domLayout prop   = "autoHeight"
                   ↳ AG Grid sizes itself to its content rows.

Container CSS     = { minHeight: 50px, maxHeight: ≈675px, overflow: hidden }
  (shortDivStyle — shortMode=true, domLayout=autoHeight)
  5 rows ≈ 105px — grid renders compactly at ~105px.
  The outer container (red border) shrinks to match.
  The 675px cap is not reached.`,
        description:
            "Even with a ¾-viewport dfvHeight, 5 rows trigger shortMode and the grid " +
            "auto-sizes to content. The large dfvHeight raises the shortMode threshold " +
            "to 29 rows, but 5 still fits comfortably below it. " +
            "The maxHeight cap of ≈675px is set but never reached.",
        whenToUse:
            "Shows that fraction-based height settings don't change the fundamental " +
            "behaviour on small datasets — shortMode keeps small tables compact regardless " +
            "of what dfvHeight is configured to. No special handling needed for small data.",
        pythonSnippet:
`w = buckaroo.BuckarooWidget(df_5rows, component_config={"height_fraction": 4/3})
# 5 rows → shortMode=true → autoHeight
# The large dfvHeight (675px) only raises the threshold; 5 rows still fits`,
        embedSnippet:
`// Same config as the ¾ viewport example; small data still auto-sizes:
component_config: { height_fraction: 4/3 }
// → 5 rows: autoHeight (grid ≈105px)
// → 500 rows: normal   (grid ≈675px)`,
    },
    {
        id: "force-normal",
        label: "Force normal (5 rows)",
        modeName: "layoutType: \"normal\" forced  (overrides shortMode auto-detect)",
        data: FIVE_ROWS,
        pinnedRows: [],
        summaryStats: [],
        compConfig: { layoutType: "normal", dfvHeight: 250 },
        outerHeight: 250,
        resolvedDomLayout: "normal",
        decisionTrace:
`component_config.layoutType = "normal"  ← explicit override

  shortMode check would have fired:
    numRows = 5, pinnedRows = 0, total = 5
    5 < maxRowsWithoutScrolling (≈18)  →  would be shortMode = true
    →  would pick  domLayout: "autoHeight"

  But layoutType is set explicitly, so auto-detect is skipped.
  →  domLayout: "normal"  (forced regardless of row count)

  dfvHeight = component_config.dfvHeight = 250
  Outer container must be 250 px.

  Same effect via React prop (fixed in #862):
    autoHeight={false}  →  stamps layoutType: "normal" client-side`,
        agGridSaw:
`domLayout prop   = "normal"
                   ↳ AG Grid fills 100% of its parent container's height.

Container CSS     = { height: 250px, overflow: hidden }
  (regularDivStyle — layoutType explicitly "normal" suppresses shortDivStyle
   even though shortMode would have been true for 5 rows)
  Without the layoutType override, shortMode=true would have produced:
    { minHeight: 50px, maxHeight: ≈450px }  and  domLayout: "autoHeight"
  With it, AG Grid gets a concrete 250px height and stays fixed.`,
        description:
            "Setting component_config.layoutType to \"normal\" bypasses the shortMode " +
            "check and forces a fixed-height grid even when the row count is small. " +
            "Without this, 5 rows would auto-detect as shortMode and shrink to content. " +
            "Pair with an explicit dfvHeight so the grid has a defined height to occupy. " +
            "In React embeds, the autoHeight={false} prop achieves the same result " +
            "client-side (see issue #862 — before the fix this prop had no effect).",
        whenToUse:
            "Entry-detail panels, sidebars, or any layout slot where the widget must " +
            "not resize when the underlying data changes. A fixed height prevents the " +
            "surrounding layout from reflowing when rows are added or filtered out.",
        pythonSnippet:
`# Force fixed height on a small table:
w = buckaroo.BuckarooWidget(df, component_config={
    "layoutType": "normal",
    "dfvHeight":  250,
})

# The shortMode check is skipped; grid takes 250 px regardless of row count.`,
        embedSnippet:
`// Via the autoHeight prop — preferred for React embeds (fixed in #862):
<BuckarooServerView
  wsUrl="ws://..."
  autoHeight={false}  // stamps layoutType:"normal", ignores server value
/>

// Or via component_config (Python/server side):
{ "layoutType": "normal", "dfvHeight": 250 }`,
    },
];

// ─── threshold explanation ────────────────────────────────────────────────────
// Shown collapsed under "How Buckaroo decided" on every panel.

const THRESHOLD_EXPLANATION =
`maxRowsWithoutScrolling = floor(dfvHeight / rowHeight) - scrollSlop

  dfvHeight   The pixel height of the AG Grid viewport (see dfvHeight
              resolution order in the reference below).
              Example at 900 px viewport, default settings:
                dfvHeight = window.innerHeight / 2 = 450 px

  rowHeight   Actual rendered height of one data row in pixels.
              Passed in from the AG Grid theme; defaults to 21 px when
              not provided. When a custom rowHeight IS provided,
              shortMode auto-detection is disabled entirely — set
              layoutType explicitly instead.

  scrollSlop  Fixed buffer of 3 rows subtracted from the estimate.
              Accounts for the status bar and other widget chrome that
              consumes vertical space inside dfvHeight.

Example:
  floor(450 / 21) - 3  =  floor(21.4) - 3  =  21 - 3  =  18

  numRows + pinnedRows  <  18  →  shortMode = true  →  autoHeight
  numRows + pinnedRows  ≥  18  →  shortMode = false →  normal

The threshold is recomputed on every render, so resizing the browser
window can change which mode fires if dfvHeight tracks the viewport
(height_fraction mode).`;

// ─── layout type reference ────────────────────────────────────────────────────
// Shown at the bottom of every explanation panel.

const LAYOUT_REFERENCE =
`─── Buckaroo concepts (component_config keys) ───────────────────────────────

  layoutType       Buckaroo config option. Controls which domLayout value is
                   sent to AG Grid. When omitted, Buckaroo auto-detects via
                   the shortMode check.
                     "autoHeight" → AG Grid domLayout="autoHeight"
                     "normal"     → AG Grid domLayout="normal"
                                    REQUIRES dfvHeight or height_fraction.

  shortMode        Buckaroo internal flag — not a config option you set.
                   Computed on every render from row counts vs the scroll
                   threshold. Drives the auto-detect path when layoutType
                   is omitted.
                     true  →  domLayout="autoHeight"
                     false →  domLayout="normal"

  dfvHeight        Pixel height of the AG Grid container div. Overrides the
                   height_fraction default. Must match your outer container.

  height_fraction  Sets dfvHeight = window.innerHeight / height_fraction.
                   Default = 2 (half viewport). Larger = shorter widget.

─── AG Grid concepts ────────────────────────────────────────────────────────

  domLayout        AG Grid prop written by Buckaroo. Not set directly by
                   callers — set via component_config.layoutType instead.
                     "autoHeight"  grid sizes itself to its content rows
                     "normal"      grid fills its parent container's height
                   Docs: https://www.ag-grid.com/javascript-data-grid/grid-size/#dom-layout

─── React-embed prop ────────────────────────────────────────────────────────

  autoHeight       Prop on BuckarooServerView / DFViewerInfiniteDS.
                   Overrides whatever layoutType the server sent.
                     true    stamps layoutType: "autoHeight"
                     false   stamps layoutType: "normal"  (fixed in #862)
                     omitted server's layoutType wins (or auto-detect)

─── dfvHeight resolution order ──────────────────────────────────────────────

  1. component_config.dfvHeight           explicit pixels
  2. window.innerHeight / height_fraction default fraction = 2 → 50vh`;

// ─── explanation panel ────────────────────────────────────────────────────────

const CODE_STYLE: React.CSSProperties = {
    background: "#1e1e2e",
    color: "#cdd6f4",
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
    fontSize: 12,
    lineHeight: 1.6,
    padding: "12px 16px",
    borderRadius: 6,
    overflowX: "auto",
    margin: "8px 0 16px",
    whiteSpace: "pre",
};

const DECISION_STYLE: React.CSSProperties = {
    background: "#f8f9fa",
    border: "1px solid #dadce0",
    borderLeft: "4px solid #1a73e8",
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
    fontSize: 12,
    lineHeight: 1.7,
    padding: "10px 14px",
    borderRadius: "0 4px 4px 0",
    overflowX: "auto",
    margin: "8px 0 16px",
    whiteSpace: "pre",
    color: "#333",
};

const SECTION_LABEL: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#888",
    margin: "16px 0 4px",
};

const BADGE_AUTO: React.CSSProperties = {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: 12,
    fontSize: 12,
    fontWeight: 600,
    background: "#e6f4ea",
    color: "#137333",
    marginLeft: 8,
    verticalAlign: "middle",
};

const BADGE_NORMAL: React.CSSProperties = {
    ...BADGE_AUTO,
    background: "#e8f0fe",
    color: "#1a73e8",
};

const AG_GRID_DOMLAYOUT_URL = "https://www.ag-grid.com/javascript-data-grid/grid-size/#dom-layout";

function ExplanationPanel({ cfg }: { cfg: HeightConfig }) {
    const badgeStyle = cfg.resolvedDomLayout === "autoHeight" ? BADGE_AUTO : BADGE_NORMAL;
    const badge = (
        <a href={AG_GRID_DOMLAYOUT_URL} target="_blank" rel="noreferrer"
           style={{ ...badgeStyle, textDecoration: "none" }}>
            domLayout: "{cfg.resolvedDomLayout}"
        </a>
    );

    return (
        <div style={{ padding: "16px 24px 32px", fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: 14, lineHeight: 1.7, color: "#333" }}>

            <h2 style={{ margin: "0 0 4px", fontSize: 17, fontWeight: 600 }}>
                {cfg.modeName} {badge}
            </h2>
            <p style={{ margin: "0 0 12px", color: "#444" }}>{cfg.description}</p>

            <p style={SECTION_LABEL}>How Buckaroo decided</p>
            <pre style={DECISION_STYLE}>{cfg.decisionTrace}</pre>

            <details style={{ marginBottom: 4 }}>
                <summary style={{ fontSize: 12, color: "#666", cursor: "pointer", userSelect: "none" }}>
                    How maxRowsWithoutScrolling is computed
                </summary>
                <pre style={{ ...DECISION_STYLE, marginTop: 6, borderLeftColor: "#aaa", fontSize: 11 }}>{THRESHOLD_EXPLANATION}</pre>
            </details>

            <p style={SECTION_LABEL}>What AG Grid saw</p>
            <pre style={{ ...DECISION_STYLE, borderLeftColor: "#fbbc04" }}>{cfg.agGridSaw}</pre>

            <p style={SECTION_LABEL}>When to use</p>
            <p style={{ margin: "0 0 12px", color: "#444" }}>{cfg.whenToUse}</p>

            <p style={SECTION_LABEL}>Python / Jupyter</p>
            <pre style={CODE_STYLE}>{cfg.pythonSnippet}</pre>

            <p style={SECTION_LABEL}>React embed</p>
            <pre style={CODE_STYLE}>{cfg.embedSnippet}</pre>

            <p style={{ ...SECTION_LABEL, marginTop: 24 }}>layoutType & dfvHeight reference</p>
            <pre style={{ ...DECISION_STYLE, borderLeftColor: "#888" }}>{LAYOUT_REFERENCE}</pre>

            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#aaa" }}>
                Red border = outer boundary of the embed. Source:{" "}
                <code style={{ fontSize: 11 }}>heightStyle()</code> in{" "}
                <code style={{ fontSize: 11 }}>gridUtils.ts</code>.
            </p>
        </div>
    );
}

// ─── widget display ───────────────────────────────────────────────────────────

function WidgetSection({ cfg }: { cfg: HeightConfig }) {
    const noop = React.useCallback<SetColumnFunc>(() => {}, []);
    const dataWrapper = React.useMemo(() => makeRaw(cfg.data), [cfg.data]);
    const colConfig = React.useMemo(
        () => makeColConfig(cfg.pinnedRows, cfg.compConfig),
        [cfg.pinnedRows, cfg.compConfig],
    );
    const summaryStats = cfg.summaryStats.length > 0 ? cfg.summaryStats : undefined;

    const outerStyle: React.CSSProperties = {
        border: "3px solid red",
        boxSizing: "border-box",
        width: "100%",
        ...(cfg.outerHeight !== undefined ? { height: cfg.outerHeight } : {}),
    };

    return (
        <div style={{ padding: "0 24px 0" }}>
            <div style={outerStyle}>
                <DFViewerInfinite
                    data_wrapper={dataWrapper}
                    df_viewer_config={colConfig}
                    summary_stats_data={summaryStats}
                    setActiveCol={noop}
                />
            </div>
        </div>
    );
}

// ─── app ──────────────────────────────────────────────────────────────────────

const BTN_BASE: React.CSSProperties = {
    padding: "6px 14px",
    border: "1px solid #ccc",
    borderRadius: 4,
    background: "#fff",
    fontSize: 13,
    cursor: "pointer",
    whiteSpace: "nowrap",
    transition: "background 0.1s, border-color 0.1s",
};

const BTN_ACTIVE: React.CSSProperties = {
    ...BTN_BASE,
    background: "#1a73e8",
    borderColor: "#1a73e8",
    color: "#fff",
    fontWeight: 600,
};

function HeightModesApp() {
    const [activeId, setActiveId] = React.useState(CONFIGS[0].id);
    const cfg = CONFIGS.find((c) => c.id === activeId) ?? CONFIGS[0];

    return (
        <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden", background: "#fafafa" }}>
            {/* button bar */}
            <div style={{
                flex: "0 0 auto",
                display: "flex",
                gap: 8,
                alignItems: "center",
                padding: "8px 24px",
                background: "#fff",
                borderBottom: "1px solid #e0e0e0",
                overflowX: "auto",
            }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#666", marginRight: 4, whiteSpace: "nowrap" }}>HEIGHT MODE:</span>
                {CONFIGS.map((c) => (
                    <button
                        key={c.id}
                        style={c.id === activeId ? BTN_ACTIVE : BTN_BASE}
                        onClick={() => setActiveId(c.id)}
                    >
                        {c.label}
                    </button>
                ))}
            </div>

            {/* widget area */}
            <div style={{ flex: "0 0 auto", paddingTop: 16 }}>
                <WidgetSection key={cfg.id} cfg={cfg} />
            </div>

            {/* explanation panel */}
            <div style={{
                flex: "1 1 0",
                overflowY: "auto",
                borderTop: "1px solid #e8e8e8",
                marginTop: 12,
                background: "#fff",
                minHeight: 180,
            }}>
                <ExplanationPanel cfg={cfg} />
            </div>
        </div>
    );
}

// ─── entry point ──────────────────────────────────────────────────────────────

const rootEl = document.getElementById("root");
if (rootEl) {
    ReactDOM.createRoot(rootEl).render(<HeightModesApp />);
}
