import { BuckarooState } from '../components/WidgetTypes';
import { IModel } from './IModel';
/** What the scheduler needs of a model. */
export type StatsModel = Pick<IModel, "get" | "on" | "off" | "send">;
/** The fields of buckaroo_state the server reruns the dataflow for, and so
 *  bumps stats_gen on. Mirrors _DATAFLOW_FIELDS in
 *  buckaroo/server/websocket_handler.py. */
export declare const DATAFLOW_STATE_FIELDS: readonly ["post_processing", "cleaning_method", "quick_command_args"];
/** Whether `next` differs from `prev` in a dataflow field. False when there is
 *  no earlier state to compare with. */
export declare function touchesDataflow(prev: BuckarooState | undefined, next: BuckarooState | undefined): boolean;
/** The model key that holds the grid's column names currently on screen. */
export declare const VISIBLE_COLUMNS_KEY = "visible_columns";
/** Record the columns the grid shows, for the next `stats_request` to carry as
 *  its `columns` hint. An empty list means none are known. */
export declare function setVisibleColumns(model: Pick<IModel, "set">, columns: string[]): void;
export interface StatsRequestOptions {
    /** Ask for stats the server did not plan to compute. The "Compute summary
     *  stats" control sends this. */
    force?: boolean;
    /** The tier asked for. */
    tier?: string;
    /** The columns the request is for. A forced request names the columns it
     *  is for or none, so the grid's columns are not added to it. A request
     *  that is not forced carries them as a hint when it names none. */
    columns?: string[];
}
/**
 * Send a time-boxed `stats_request` for the stats_gen of the state the model
 * shows. The scheduler's requests carry the columns the grid shows as the hint,
 * when they are known; a request that names its columns carries those instead,
 * and a forced one carries only those. Returns false, and sends nothing, when
 * the model's df_meta carries no stats.gen.
 */
export declare function requestStats(model: Pick<IModel, "get" | "send">, opts?: StatsRequestOptions): boolean;
/** The model key that records a run the user started, for the scheduler to
 *  continue. */
export declare const FORCED_RUN_KEY = "stats_forced";
/** What forceStats records under FORCED_RUN_KEY. */
export interface ForcedRun {
    gen: number;
    tier: string;
    columns?: string[];
}
/**
 * The "Compute summary stats" control: ask for stats the server did not plan to
 * compute, `stats_request {force: true, tier}`. The tier is the smallest the
 * server allows above the one reached (scalar before full), and `opts.columns`
 * is the per-column form. Sends nothing, and returns false, when no tier is
 * left to ask for or df_meta carries no stats.gen.
 *
 * The stats are marked pending in a new df_meta. The server sends no frame to a
 * capable client, so without this the loading text and the placeholder rows
 * would wait for the first reply, and the control would stay on screen to be
 * clicked again. A final reply, a refusal or a frame from the server puts the
 * status it names in place of it.
 *
 * The run is recorded on the model, where a scheduler started on it picks it up
 * and answers each reply that is not final with the same request.
 */
export declare function forceStats(model: Pick<IModel, "get" | "set" | "send">, opts?: {
    columns?: string[];
}): boolean;
export interface OrchestratorOptions {
    model: StatsModel;
    /** Lower bound on the delay before asking for a new state's stats. Default 200 ms. */
    minDebounceMs?: number;
    /** Upper bound on that delay. Default 3000 ms. */
    maxDebounceMs?: number;
    /** Multiplier on the last observed request time. Default 2. */
    multiplier?: number;
    /** Request time assumed until one has been observed. Default 250 ms. */
    initialRequestMs?: number;
    /** How long to wait for the first rows before asking anyway (an empty
     *  frame, the summary view, and a grid that never fetches send none).
     *  Default 1500 ms. */
    firstPaintTimeoutMs?: number;
}
export declare class StateOrchestrator {
    private readonly model;
    private readonly minDebounceMs;
    private readonly maxDebounceMs;
    private readonly multiplier;
    private readonly initialRequestMs;
    private readonly firstPaintTimeoutMs;
    private started;
    private run;
    private runKey;
    private basis;
    private doneKey;
    private inFlight;
    private delayMs;
    private began;
    private sentAt;
    private lastRequestMs;
    private requestTimer;
    private paintTimer;
    private syncQueued;
    private seenMeta;
    private seenDict;
    private seenState;
    private seenForced;
    constructor(opts: OrchestratorOptions);
    /** Start watching the model, and adopt the state it already holds. */
    start(): void;
    /** Stop watching and cancel anything scheduled. Call on unmount. */
    stop(): void;
    /**
     * The delay (ms) before asking for a new state's stats: the last observed
     * request time times the multiplier, clamped to
     * `[minDebounceMs, maxDebounceMs]`. A request that took longer means the
     * server was busy, so the next one waits longer.
     */
    computeDebounce(): number;
    private readonly onModelChange;
    private readonly onState;
    private readonly onMessage;
    private sync;
    private desiredRun;
    private adoptForced;
    private syncForced;
    private basisChanged;
    private begin;
    private standDown;
    private markPainted;
    private arm;
    private fire;
    private noteRequestTime;
    private clearTimers;
}
