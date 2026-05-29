import { StoryObj } from '@storybook/react';
import { DFData, DFViewerConfig } from '../components/DFViewerParts/DFWhole';
import { DatasourceOrRaw } from '../components/DFViewerParts/DFViewerDataHelper';
declare const meta: {
    title: string;
    component: ({ data_wrapper, df_viewer_config, summary_stats_data, outerHeight, }: {
        data_wrapper: DatasourceOrRaw;
        df_viewer_config: DFViewerConfig;
        summary_stats_data?: DFData;
        /** Outer container height in px. Omit for autoHeight stories. */
        outerHeight?: number;
    }) => import("react/jsx-runtime").JSX.Element;
    parameters: {
        layout: string;
    };
    tags: string[];
    argTypes: {
        data_wrapper: {
            control: false;
        };
        df_viewer_config: {
            control: false;
        };
        summary_stats_data: {
            control: false;
        };
        outerHeight: {
            control: {
                type: "number";
            };
            description: string;
        };
    };
};
export default meta;
type Story = StoryObj<typeof meta>;
/**
 * 5 rows fit without scrolling, so Buckaroo auto-detects `shortMode` and
 * switches to `domLayout: "autoHeight"`. The grid and outer container grow to
 * content height — no explicit sizing needed.
 */
export declare const FiveRows: Story;
/**
 * Pinned rows count toward the `shortMode` threshold. 10 pinned stat rows +
 * 5 data rows still fit without scrolling, so `autoHeight` is still
 * auto-detected. Pinned rows appear above the scrollable data area.
 */
export declare const FiveRowsTenPinned: Story;
/**
 * 500 rows exceed the scroll threshold, so Buckaroo switches to
 * `domLayout: "normal"` with a fixed height. Here `dfvHeight: 400` is set
 * explicitly and the outer container matches.
 */
export declare const FiveHundredRows: Story;
/**
 * 500 rows in `normal` mode with 10 stat rows pinned to the top of the grid.
 * Pinned rows stay visible while data rows scroll beneath them.
 */
export declare const FiveHundredRowsTenPinned: Story;
/**
 * `component_config.dfvHeight` sets an explicit pixel height for the grid,
 * overriding the default of `window.innerHeight / 2`. Set the outer container
 * to the same value. Here `dfvHeight: 200` makes a compact embed.
 */
export declare const ExplicitHeight200: Story;
/**
 * `component_config.height_fraction = 4` sets `dfvHeight = window.innerHeight / 4`.
 * The grid height tracks the browser window — resize to see it update.
 */
export declare const HeightFraction4: Story;
/**
 * `component_config.layoutType: "autoHeight"` forces the grid to grow to all
 * rows regardless of count. Use only in hosts where vertical space is
 * unconstrained (e.g. a notebook-style cell stack).
 */
export declare const ForceAutoHeight: Story;
/**
 * `component_config.layoutType: "normal"` forces a fixed-height grid even for
 * small datasets. Useful for fixed-height panels (e.g. an entry-detail sidebar)
 * where the embed must not resize with the data. See also the `autoHeight` prop
 * on `BuckarooServerView` / `DFViewerInfiniteDS`, fixed in #862.
 */
export declare const ForceNormal: Story;
