/**
 * Client-side scheduler for the JS-driven progressive-stats protocol.
 *
 * On a state_change, ships the cheap (scalar) request immediately so
 * df_meta + scalar pinned rows update fast. Schedules the expensive
 * (aggregate) compute per scope behind an adaptive debounce — by
 * default 2× the last observed aggregate compute time for that scope,
 * clamped to ``[minDebounceMs, maxDebounceMs]``.
 *
 * Token-based cancellation: every state_change bumps an internal
 * token; results carrying a stale token are dropped on arrival.
 *
 * See plans/js-driven-stat-debounce.md for the full protocol design.
 *
 * This module is transport-agnostic — pass any object with a
 * ``send(s: string)`` method. Existing buckaroo WS connections fit.
 */
export type ScopeName = "raw" | "clean" | "filt";
export type CostGroup = "scalar" | "aggregate";
export interface WsLike {
    send(message: string): void;
}
export interface OrchestratorOptions {
    ws: WsLike;
    /** Lower bound on the per-scope debounce. Default 200 ms. */
    minDebounceMs?: number;
    /** Upper bound on the per-scope debounce. Default 3000 ms. */
    maxDebounceMs?: number;
    /** Multiplier on the last observed aggregate compute time. Default 2. */
    multiplier?: number;
    /** Initial aggregate baseline per scope (used until we observe a real one). */
    initialAggregateMs?: Partial<Record<ScopeName, number>>;
}
export interface StatGroupResult {
    type: "stat_group_result";
    state_token: number;
    scope: ScopeName;
    group: CostGroup;
    elapsed_ms: number;
    stats?: unknown;
}
export declare class StateOrchestrator {
    private token;
    private aggregateTimers;
    private lastAggregateMs;
    private readonly ws;
    private readonly minDebounceMs;
    private readonly maxDebounceMs;
    private readonly multiplier;
    /** Fallback baseline before any real aggregate compute has been observed. */
    private readonly defaultBaselineMs;
    constructor(opts: OrchestratorOptions);
    /**
     * Current state-change token. Tests inspect this; production
     * code doesn't usually need it.
     */
    get currentToken(): number;
    /**
     * Compute the debounce delay (ms) for a given scope based on
     * the last observed aggregate compute time, clamped to
     * ``[minDebounceMs, maxDebounceMs]``.
     */
    computeDebounce(scope: ScopeName): number;
    /**
     * Drive a single user-initiated state change.
     *
     *   1. Bump the state token.
     *   2. Cancel any pending aggregate timers from the previous change.
     *   3. Ship the ``state_change`` message (server will reply with
     *      the scalar stats fast).
     *   4. For each scope expected to have aggregate work, schedule a
     *      debounced ``compute_stat_group`` request. Timer fires the
     *      request only if no further state_change has bumped the
     *      token meanwhile.
     */
    onStateChange(newState: Record<string, unknown>, opts?: {
        scopesForAggregate?: ScopeName[];
    }): void;
    /**
     * Process a ``stat_group_result`` from the server. Stale results
     * (mismatched token) are silently ignored. Successful results
     * update the per-scope aggregate baseline used by the next
     * debounce.
     *
     * Returns true if the result was applied, false if it was stale.
     */
    onStatGroupResult(msg: StatGroupResult): boolean;
    /** Cancel all pending aggregate timers. Call on widget unmount. */
    dispose(): void;
}
