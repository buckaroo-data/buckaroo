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
export interface StatsRequestOptions {
    /** Ask for stats the server did not plan to compute. The "Compute summary
     *  stats" control sends this. */
    force?: boolean;
}
/**
 * Send a `stats_request` for the stats_gen of the state the model shows.
 * Returns false, and sends nothing, when its df_meta carries no stats.gen.
 */
export declare function requestStats(model: Pick<IModel, "get" | "send">, opts?: StatsRequestOptions): boolean;
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
    private gen;
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
    private begin;
    private standDown;
    private markPainted;
    private arm;
    private fire;
    private noteRequestTime;
    private clearTimers;
}
