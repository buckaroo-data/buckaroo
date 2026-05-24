import type { Meta, StoryObj } from "@storybook/react";

import "../style/dcf-npm.css";
import { DFViewer } from "../components/DFViewerParts/DFViewerInfinite";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";

/**
 * Direct `<DFViewer>` consumer pattern — no wrapper component, no hooks
 * in a `render` function. `meta.component` is `DFViewer` itself and each
 * story passes prop values via `args:`, so Storybook's "Show code" view
 * displays the actual JSX an `npm install buckaroo-js-core` consumer
 * would paste into their React app (literal `df_data` array, literal
 * `df_viewer_config` object), not a `render()` arrow function.
 *
 * A `decorators` entry wraps the rendered output in a sized container —
 * decorators are not part of the "Show code" output, so they keep the
 * story functional without obscuring the consumer-facing API.
 */

const meta: Meta<typeof DFViewer> = {
    title: "Buckaroo/Direct/DFViewer",
    component: DFViewer,
    parameters: { layout: "centered" },
    decorators: [
        (Story) => (
            <div style={{ width: 720, height: 400 }}>
                <Story />
            </div>
        ),
    ],
    tags: ["autodocs"],
} satisfies Meta<typeof DFViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

const df_data: DFData = [
    { index: 0, region: "North", revenue: 12500, units: 320 },
    { index: 1, region: "South", revenue: 9800, units: 240 },
    { index: 2, region: "East", revenue: 15700, units: 410 },
    { index: 3, region: "West", revenue: 11200, units: 290 },
    { index: 4, region: "Central", revenue: 7300, units: 175 },
];

const df_viewer_config: DFViewerConfig = {
    column_config: [
        {
            col_name: "region",
            header_name: "Region",
            displayer_args: { displayer: "string" },
        },
        {
            col_name: "revenue",
            header_name: "Revenue ($)",
            displayer_args: {
                displayer: "float",
                min_fraction_digits: 0,
                max_fraction_digits: 0,
            },
            color_map_config: {
                color_rule: "color_map",
                val_column: "revenue",
                map_name: "BLUE_TO_YELLOW",
            },
        },
        {
            col_name: "units",
            header_name: "Units",
            displayer_args: { displayer: "integer", min_digits: 1, max_digits: 4 },
        },
    ],
    pinned_rows: [],
    left_col_configs: [
        {
            col_name: "index",
            header_name: "#",
            displayer_args: { displayer: "string" },
        },
    ],
};

// Storybook's autodocs source printer puts every array element on its own
// line, which turns df_data into a tall column of one-property-per-line
// rows. Override with a hand-curated snippet so the "Show code" view
// reads the way an npm consumer would actually write the call.
const PRIMARY_SOURCE = `<DFViewer
  df_data={[
    { index: 0, region: "North",   revenue: 12500, units: 320 },
    { index: 1, region: "South",   revenue:  9800, units: 240 },
    { index: 2, region: "East",    revenue: 15700, units: 410 },
    { index: 3, region: "West",    revenue: 11200, units: 290 },
    { index: 4, region: "Central", revenue:  7300, units: 175 },
  ]}
  df_viewer_config={{
    column_config: [
      { col_name: "region",  header_name: "Region",      displayer_args: { displayer: "string" } },
      { col_name: "revenue", header_name: "Revenue ($)", displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 }, color_map_config: { color_rule: "color_map", val_column: "revenue", map_name: "BLUE_TO_YELLOW" } },
      { col_name: "units",   header_name: "Units",       displayer_args: { displayer: "integer" } },
    ],
    pinned_rows: [],
    left_col_configs: [
      { col_name: "index", header_name: "#", displayer_args: { displayer: "string" } },
    ],
  }}
/>`;

export const Primary: Story = {
    args: {
        df_data,
        df_viewer_config,
    },
    parameters: {
        docs: { source: { code: PRIMARY_SOURCE } },
    },
};
