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

export class StateOrchestrator {
    private token = 0;
    private aggregateTimers = new Map<ScopeName, ReturnType<typeof setTimeout>>();
    private lastAggregateMs = new Map<ScopeName, number>();
    private readonly ws: WsLike;
    private readonly minDebounceMs: number;
    private readonly maxDebounceMs: number;
    private readonly multiplier: number;
    /** Fallback baseline before any real aggregate compute has been observed. */
    private readonly defaultBaselineMs = 500;

    constructor(opts: OrchestratorOptions) {
        this.ws = opts.ws;
        this.minDebounceMs = opts.minDebounceMs ?? 200;
        this.maxDebounceMs = opts.maxDebounceMs ?? 3000;
        this.multiplier = opts.multiplier ?? 2;
        if (opts.initialAggregateMs) {
            for (const [scope, ms] of Object.entries(opts.initialAggregateMs)) {
                if (ms != null) this.lastAggregateMs.set(scope as ScopeName, ms);
            }
        }
    }

    /**
     * Current state-change token. Tests inspect this; production
     * code doesn't usually need it.
     */
    get currentToken(): number {
        return this.token;
    }

    /**
     * Compute the debounce delay (ms) for a given scope based on
     * the last observed aggregate compute time, clamped to
     * ``[minDebounceMs, maxDebounceMs]``.
     */
    computeDebounce(scope: ScopeName): number {
        const last = this.lastAggregateMs.get(scope) ?? this.defaultBaselineMs;
        const raw = last * this.multiplier;
        return Math.max(this.minDebounceMs, Math.min(this.maxDebounceMs, raw));
    }

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
    onStateChange(
        newState: Record<string, unknown>,
        opts?: { scopesForAggregate?: ScopeName[] },
    ): void {
        const token = ++this.token;
        for (const t of this.aggregateTimers.values()) clearTimeout(t);
        this.aggregateTimers.clear();

        this.ws.send(JSON.stringify({
            type: "state_change",
            state_token: token,
            new_state: newState,
        }));

        const scopes = opts?.scopesForAggregate ?? ["filt"];
        for (const scope of scopes) {
            const delay = this.computeDebounce(scope);
            const tid = setTimeout(() => {
                // If a newer state_change bumped the token while we
                // were waiting, drop the request — sending it would
                // produce a stat_group_aborted from the server anyway.
                if (token !== this.token) return;
                this.ws.send(JSON.stringify({
                    type: "compute_stat_group",
                    state_token: token,
                    scope,
                    group: "aggregate",
                }));
            }, delay);
            this.aggregateTimers.set(scope, tid);
        }
    }

    /**
     * Process a ``stat_group_result`` from the server. Stale results
     * (mismatched token) are silently ignored. Successful results
     * update the per-scope aggregate baseline used by the next
     * debounce.
     *
     * Returns true if the result was applied, false if it was stale.
     */
    onStatGroupResult(msg: StatGroupResult): boolean {
        if (msg.state_token !== this.token) return false;
        this.lastAggregateMs.set(msg.scope, msg.elapsed_ms);
        return true;
    }

    /** Cancel all pending aggregate timers. Call on widget unmount. */
    dispose(): void {
        for (const t of this.aggregateTimers.values()) clearTimeout(t);
        this.aggregateTimers.clear();
    }
}
