export interface DFMeta {
    total_rows: number;
    columns: number;
    filtered_rows: number;
    rows_shown: number;
}
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
