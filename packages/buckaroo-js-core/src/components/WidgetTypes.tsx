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

// Stubs: the real helpers come with the fix.
export const statsRequestable = (_stats: DFMetaStats | undefined): string[] => [];
export const statsAutoRequest = (_stats: DFMetaStats | undefined): boolean => false;
export const nextRequestTier = (_stats: DFMetaStats | undefined): StatsTier | undefined => undefined;
export const canRequestStats = (_stats: DFMetaStats | undefined): boolean => false;
export const demandTier = (_stats: DFMetaStats | undefined): StatsTier | undefined => undefined;
export const statsOverCeiling = (_stats: DFMetaStats | undefined): boolean => false;

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
