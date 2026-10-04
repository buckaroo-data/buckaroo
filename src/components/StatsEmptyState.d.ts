import { ThemeConfig } from './DFViewerParts/gridUtils';
import { DFMetaStats } from './WidgetTypes';
/** A column the empty state can compute stats for on its own. */
export interface StatsColumnOption {
    /** The grid's own column name (a, b, c), which a request names. */
    field: string;
    /** What the column is called on screen. */
    label: string;
}
export interface StatsEmptyStateProps {
    stats: DFMetaStats;
    /** The columns of the table, for the per-column form. Without them the form
     *  is the whole-table button alone. */
    columns?: StatsColumnOption[];
    /** Asks the server for the stats: no argument for the whole table, `columns`
     *  for the per-column form. Without it the state is the message alone. */
    onComputeStats?: (opts?: {
        columns?: string[];
    }) => void;
    themeConfig?: ThemeConfig;
}
/**
 * The size the server's decision rested on, as "12.4M rows x 44 columns". A
 * million rows and over read as a compact count. Empty when the server sent no
 * estimate.
 */
export declare function formatStatsEstimate(estimate: DFMetaStats["estimate"]): string;
/** Why the stats were not computed, in a sentence: the server's reason for a
 *  session that is not computed, with the size when it sent one. A session at
 *  the server's ceiling reads as over the size limit, however the server put it. */
export declare function notComputedMessage(stats: DFMetaStats): string;
/**
 * What the summary view shows while the stats are not computed: why, and the
 * control that asks for them. The control is one button for the next tier the
 * server allows (basic before full), with a picker that limits it to one column.
 * A session the server's ceiling refused gets the message and nothing else.
 */
export declare function StatsEmptyState({ stats, columns, onComputeStats, themeConfig }: StatsEmptyStateProps): import("react/jsx-runtime").JSX.Element;
