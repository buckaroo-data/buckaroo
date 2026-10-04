import { useState } from "react";
import { resolveColorScheme, resolveThemeColors } from "./DFViewerParts/gridUtils";
import type { ThemeConfig } from "./DFViewerParts/gridUtils";
import { useColorScheme } from "./useColorScheme";
import { DFMetaStats, canRequestStats, nextRequestTier, statsOverCeiling } from "./WidgetTypes";

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
    onComputeStats?: (opts?: { columns?: string[] }) => void;
    themeConfig?: ThemeConfig;
}

const countFormat = new Intl.NumberFormat("en-US");
const compactFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

const plural = (n: number, noun: string): string => (n === 1 ? `1 ${noun}` : `${countFormat.format(n)} ${noun}s`);

/**
 * The size the server's decision rested on, as "12.4M rows x 44 columns". A
 * million rows and over read as a compact count. Empty when the server sent no
 * estimate.
 */
export function formatStatsEstimate(estimate: DFMetaStats["estimate"]): string {
    const parts: string[] = [];
    if (typeof estimate?.rows === "number") {
        parts.push(estimate.rows >= 1_000_000 ? `${compactFormat.format(estimate.rows)} rows` : plural(estimate.rows, "row"));
    }
    if (typeof estimate?.cols === "number") parts.push(plural(estimate.cols, "column"));
    return parts.join(" x ");
}

/** Why the stats were not computed, in a sentence: the server's reason for a
 *  session that is not computed, with the size when it sent one. A session at
 *  the server's ceiling reads as over the size limit, however the server put it. */
export function notComputedMessage(stats: DFMetaStats): string {
    const size = formatStatsEstimate(stats.estimate);
    const sizeSuffix = size === "" ? "" : ` (${size})`;
    switch (statsOverCeiling(stats) ? "ceiling" : stats.reason) {
        case "ceiling":
            return `Summary stats are not available for this table: it is over the size limit${sizeSuffix}.`;
        case "size":
            return `Summary stats were not computed for this table because it is large${sizeSuffix}.`;
        case "host":
            return `Summary stats were turned off for this table${sizeSuffix}.`;
        case "cost":
            return `Summary stats were paused because computing them was taking too long${sizeSuffix}.`;
        default:
            return `Summary stats are not computed for this table${sizeSuffix}.`;
    }
}

const TIER_DETAILS: Record<string, { label: string; title: string }> = {
    scalar: { label: "Compute basic stats", title: "Null counts, min, max, mean and std for each column" },
    full: { label: "Compute full stats", title: "Every summary stat, with histograms and value counts. Slower." },
};

/**
 * What the summary view shows while the stats are not computed: why, and the
 * control that asks for them. The control is one button for the next tier the
 * server allows (basic before full), with a picker that limits it to one column.
 * A session the server's ceiling refused gets the message and nothing else.
 */
export function StatsEmptyState({ stats, columns = [], onComputeStats, themeConfig }: StatsEmptyStateProps) {
    const osColorScheme = useColorScheme();
    const scheme = resolveColorScheme(osColorScheme, themeConfig);
    const colors = resolveThemeColors(scheme, themeConfig);
    const [picked, setPicked] = useState("");

    const tier = nextRequestTier(stats);
    const canCompute = onComputeStats !== undefined && canRequestStats(stats);
    const column = columns.some((c) => c.field === picked) ? picked : "";
    const details = TIER_DETAILS[tier ?? ""] ?? TIER_DETAILS.full;
    const label = stats.reason === "cost" ? "Continue computing stats" : details.label;

    return (
        <div
            className="bk-stats-empty"
            data-testid="stats-empty-state"
            data-stats-reason={stats.reason}
            style={{
                backgroundColor: colors?.backgroundColor || (scheme === "light" ? "#ffffff" : "#181D1F"),
                color: colors?.foregroundColor || (scheme === "light" ? "#181D1F" : "#e8e8e8"),
            }}
        >
            <p className="bk-stats-empty-message">{notComputedMessage(stats)}</p>
            {canCompute ? (
                <div className="bk-stats-empty-control">
                    {columns.length > 0 ? (
                        <select aria-label="Columns to compute" value={column} onChange={(e) => setPicked(e.target.value)}>
                            <option value="">All columns</option>
                            {columns.map((c) => (
                                <option key={c.field} value={c.field}>
                                    {c.label}
                                </option>
                            ))}
                        </select>
                    ) : null}
                    <button
                        type="button"
                        title={details.title}
                        onClick={() => (column === "" ? onComputeStats() : onComputeStats({ columns: [column] }))}
                    >
                        {label}
                    </button>
                </div>
            ) : null}
        </div>
    );
}
