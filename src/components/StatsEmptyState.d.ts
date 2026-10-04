import { DFMetaStats } from './WidgetTypes';
import { ThemeConfig } from './DFViewerParts/gridUtils';
/** A column the empty state can compute stats for on its own. */
export interface StatsColumnOption {
    /** The grid's own column name (a, b, c), which a request names. */
    field: string;
    /** What the column is called on screen. */
    label: string;
}
export interface StatsEmptyStateProps {
    stats: DFMetaStats;
    columns?: StatsColumnOption[];
    onComputeStats?: (opts?: {
        columns?: string[];
    }) => void;
    themeConfig?: ThemeConfig;
}
export declare function formatStatsEstimate(_estimate: DFMetaStats["estimate"]): string;
export declare function StatsEmptyState(_props: StatsEmptyStateProps): null;
