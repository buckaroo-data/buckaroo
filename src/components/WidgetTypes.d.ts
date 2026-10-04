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
}
export interface DFMeta {
    total_rows: number;
    columns: number;
    filtered_rows: number;
    rows_shown: number;
    stats?: DFMetaStats;
}
export declare const getStatsStatus: (meta: DFMeta | undefined) => StatsStatus;
export declare const statsRequestable: (_stats: DFMetaStats | undefined) => string[];
export declare const statsAutoRequest: (_stats: DFMetaStats | undefined) => boolean;
export declare const nextRequestTier: (_stats: DFMetaStats | undefined) => StatsTier | undefined;
export declare const canRequestStats: (_stats: DFMetaStats | undefined) => boolean;
export declare const demandTier: (_stats: DFMetaStats | undefined) => StatsTier | undefined;
export declare const statsOverCeiling: (_stats: DFMetaStats | undefined) => boolean;
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
