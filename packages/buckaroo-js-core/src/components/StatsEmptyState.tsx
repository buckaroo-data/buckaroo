import type { DFMetaStats } from "./WidgetTypes";
import type { ThemeConfig } from "./DFViewerParts/gridUtils";

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
    onComputeStats?: (opts?: { columns?: string[] }) => void;
    themeConfig?: ThemeConfig;
}

// Stub: the real functions come with the fix.
export function formatStatsEstimate(_estimate: DFMetaStats["estimate"]): string {
    return "";
}

export function StatsEmptyState(_props: StatsEmptyStateProps) {
    return null;
}
