// Where the summary stats stand, as the server reports it in df_meta.stats.
// "pending": a stats_update is expected. "not_computed": none will be sent
// unless the user asks. A missing df_meta.stats means "complete", which is
// what servers that predate the field send.
export type StatsStatus = "complete" | "pending" | "not_computed" | "error";

// The tiers a session can reach, lowest first. "schema" is dtypes and identity
// keys, "scalar" adds the cheap per-column stats (min, max, mean, std, null
// count), "full" is every stat.
export type StatsTier = "schema" | "scalar" | "full";
export const STATS_TIERS: readonly StatsTier[] = ["schema", "scalar", "full"];

export interface DFMetaStats {
    status: StatsStatus;
    // The tier reached so far.
    tier?: string;
    // Why the stats are not computed: "size", "host", "cost" or "ceiling".
    reason?: string;
    gen?: number;
    // The fields below are sent to a client that advertises stats_ondemand,
    // and only where they differ from the default noted on each.
    // The tier the session is headed for.
    tier_target?: string;
    // The numbers the server's decision rested on.
    estimate?: { rows?: number; cols?: number; bytes?: number };
    // Whether the client should ask for the stats on its own. Absent means true.
    auto_request?: boolean;
    // Tiers above the target an explicit request may still be granted. Absent
    // means ["full"].
    requestable?: string[];
    // Columns whose styling needs stats now (a color_map reads min and max).
    demand_columns?: string[];
    // Stat keys left out of the run, and keys computed from a sample.
    omitted_keys?: string[];
    approx_keys?: string[];
}

export interface DFMeta {
    // static,
    total_rows: number;
    columns: number;
    filtered_rows: number;
    rows_shown: number;
    // Absent when the server predates the two-message protocol.
    stats?: DFMetaStats;
}

export const getStatsStatus = (meta: DFMeta | undefined): StatsStatus =>
    meta?.stats?.status ?? "complete";

// What a server that leaves a policy field out means by it (see DFMetaStats).
const DEFAULT_REQUESTABLE: readonly string[] = ["full"];

export const statsRequestable = (stats: DFMetaStats | undefined): string[] =>
    stats?.requestable ?? [...DEFAULT_REQUESTABLE];

export const statsAutoRequest = (stats: DFMetaStats | undefined): boolean => stats?.auto_request !== false;

const tierRank = (tier: string | undefined): number => {
    const rank = STATS_TIERS.indexOf(tier as StatsTier);
    return rank === -1 ? 0 : rank;
};

/**
 * The tier a request for more stats should ask for: the smallest tier in
 * `requestable` above the one reached, so scalar goes before full. Names that
 * are not tiers are ignored. Undefined when there is nothing left to ask for.
 */
export const nextRequestTier = (stats: DFMetaStats | undefined): StatsTier | undefined => {
    if (stats === undefined) return undefined;
    const requestable = statsRequestable(stats);
    const reached = tierRank(stats.tier);
    return STATS_TIERS.find((tier) => requestable.includes(tier) && tierRank(tier) > reached);
};

/**
 * Whether the server's ceiling keeps the stats from being computed. It says so
 * with reason "ceiling" when the ceiling cut a request down. When the server
 * sized the session at the ceiling itself the reason is "size" and there is
 * nothing above it to ask for, which comes to the same thing for the user.
 */
export const statsOverCeiling = (stats: DFMetaStats | undefined): boolean =>
    stats?.status === "not_computed" &&
    (stats.reason === "ceiling" ||
        (stats.reason === "size" && stats.requestable !== undefined && nextRequestTier(stats) === undefined));

/** Whether the "Compute summary stats" control applies: the stats are not
 *  computed, the server's ceiling did not refuse them, and a tier is left. */
export const canRequestStats = (stats: DFMetaStats | undefined): boolean =>
    stats?.status === "not_computed" && !statsOverCeiling(stats) && nextRequestTier(stats) !== undefined;

/**
 * The tier of a request for the columns styling needs stats for (`demand_columns`):
 * the smallest tier from scalar up that the policy allows, the target included,
 * since scalar is where min and max come from. Undefined when it allows none.
 */
export const demandTier = (stats: DFMetaStats | undefined): StatsTier | undefined => {
    if (stats === undefined) return undefined;
    const allowed = [...statsRequestable(stats), ...(stats.tier_target === undefined ? [] : [stats.tier_target])];
    return STATS_TIERS.find((tier) => tierRank(tier) >= tierRank("scalar") && allowed.includes(tier));
};

export interface BuckarooOptions {
    sampled: string[];
    cleaning_method: string[];
    post_processing: string[];
    df_display: string[]; // keys into Into df_display_args
    show_commands: string[];
}

export type QuickAtom = number | string;
export type QuickArg = QuickAtom[];
export interface BuckarooState {
    sampled: string | false;
    cleaning_method: string | false;
    quick_command_args: Record<string, QuickArg>;
    post_processing: string | false;
    df_display: string; //at least one dataframe must always be displayed
    show_commands: string | false;
}

export type BKeys = "sampled" | "cleaning_method" | "post_processing" | "df_display";

// df_dict: Record<string, DFWhole>;
// df_meta: DFMeta;
/*

  df_dict: Record<string, DFWhole>;
  df_meta: DFMeta;
  operations: Operation[];
  on_operations: (ops: Operation[]) => void;
  operation_results: OperationResult;
  commandConfig: CommandConfigT;
  buckaroo_state: BuckarooState;
  on_buckaroo_state: React.Dispatch<React.SetStateAction<BuckarooState>>;
  buckaroo_options: BuckarooOptions;
*/
