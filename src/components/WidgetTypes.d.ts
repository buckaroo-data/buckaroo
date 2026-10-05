export type StatsStatus = "complete" | "pending" | "not_computed" | "error";
export type StatsTier = "schema" | "scalar" | "full";
export declare const STATS_TIERS: readonly StatsTier[];
export interface DFMetaStats {
    status: StatsStatus;
    tier?: string;
    reason?: string;
    gen?: number;
    tier_target?: string;
    estimate?: {
        rows?: number;
        cols?: number;
        bytes?: number;
    };
    auto_request?: boolean;
    requestable?: string[];
    demand_columns?: string[];
    omitted_keys?: string[];
    approx_keys?: string[];
    computed_columns?: string[];
    reached_tier?: StatsTier;
}
export interface DFMeta {
    total_rows: number;
    columns: number;
    filtered_rows: number;
    rows_shown: number;
    stats?: DFMetaStats;
}
export declare const getStatsStatus: (meta: DFMeta | undefined) => StatsStatus;
export declare const statsRequestable: (stats: DFMetaStats | undefined) => string[];
export declare const statsAutoRequest: (stats: DFMetaStats | undefined) => boolean;
/** The higher of two tier names. A name that is not a tier counts as schema. */
export declare const higherTier: (a: string | undefined, b: string | undefined) => StatsTier;
/**
 * The highest tier the session has reached: the server's `tier` or the tier
 * StatsChannel recorded in `reached_tier`, whichever is higher. The server
 * leaves `tier` at the tier a session was published at while it is not
 * computed, so a run for the whole table that reached scalar shows only in
 * `reached_tier`.
 */
export declare const tierReached: (stats: DFMetaStats | undefined) => StatsTier;
/**
 * The tier the client should request on its own, without a click: the target
 * the server sized the session to (`tier_target`), for a session that is not
 * computed, that the server says to request for (`auto_request`, absent means
 * true) and that is neither at its ceiling nor paused on cost, while the tier
 * reached is below the target. `requestable` lists the tiers above the target,
 * so it plays no part. Undefined when there is nothing to request.
 */
export declare const autoRequestTier: (stats: DFMetaStats | undefined) => StatsTier | undefined;
/**
 * The tier a request for more stats should ask for: the smallest tier in
 * `requestable` above the one reached (see tierReached), so scalar goes before
 * full. Names that are not tiers are ignored. Undefined when there is nothing
 * left to ask for.
 */
export declare const nextRequestTier: (stats: DFMetaStats | undefined) => StatsTier | undefined;
/**
 * Whether the server's ceiling keeps the stats from being computed. It says so
 * with reason "ceiling" when the ceiling cut a request down. When the server
 * sized the session at the ceiling itself the reason is "size" and there is
 * nothing above it to ask for, which comes to the same thing for the user.
 */
export declare const statsOverCeiling: (stats: DFMetaStats | undefined) => boolean;
/** Whether the "Compute summary stats" control applies: the stats are not
 *  computed, the server's ceiling did not refuse them, and a tier is left. */
export declare const canRequestStats: (stats: DFMetaStats | undefined) => boolean;
/**
 * The tier of a request for the columns styling needs stats for (`demand_columns`):
 * the smallest tier from scalar up that the policy allows, the target included,
 * since scalar is where min and max come from. Undefined when it allows none, or
 * when the tier reached already covers it.
 */
export declare const demandTier: (stats: DFMetaStats | undefined) => StatsTier | undefined;
export interface BuckarooOptions {
    sampled: string[];
    cleaning_method: string[];
    post_processing: string[];
    df_display: string[];
    show_commands: string[];
}
export type QuickAtom = number | string;
export type QuickArg = QuickAtom[];
export interface BuckarooState {
    sampled: string | false;
    cleaning_method: string | false;
    quick_command_args: Record<string, QuickArg>;
    post_processing: string | false;
    df_display: string;
    show_commands: string | false;
}
export type BKeys = "sampled" | "cleaning_method" | "post_processing" | "df_display";
