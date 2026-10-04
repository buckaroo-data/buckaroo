/**
 * Client-side scheduler for the stats wire (rows-first c4).
 *
 * A server that defers a session's summary stats sends a first frame whose
 * `df_meta.stats.status` is "pending", then waits to be asked. This scheduler
 * asks: it sends `stats_request {stats_gen, scope: "raw", incremental: true}`
 * once the first rows have arrived, sends another for each reply that leaves
 * the stats pending (a `stats_update` that is not final), and stops when the
 * status leaves "pending". Nothing is requested unless `df_meta.stats` says
 * pending, so a session whose server reports no stats is never touched.
 *
 * Every request is a time-boxed step: the server runs units for a short
 * budget (about 75 ms) and replies with a partial `stats_update`
 * (`final: false`, the fragments that are new), which StatsChannel merges into
 * `all_stats` without leaving "pending". Each such reply is answered with the
 * next request, and the final reply, which carries the complete `all_stats`,
 * ends the run. A request also names the columns the grid shows (`columns`, the
 * grid's own column names), so the server runs the units that cover them first.
 * A server that does not know either field ignores them, runs the whole run and
 * answers with a final reply, which ends the run the same way.
 *
 * It watches the model and sends through it, so any IModel works:
 *
 *   change:df_meta         the status and stats_gen of the state on screen
 *   change:df_data_dict    a reply merged into all_stats (StatsChannel's job)
 *   change:buckaroo_state  a state change made on this client
 *   msg:custom             an infinite_resp, the first rows
 *
 * The columns the grid shows are read from the model's `visible_columns` key
 * when a request goes out (see setVisibleColumns). It is a client-side key: the
 * server never sends it.
 *
 * The merge is not here. A reply reaches this class only as a change on the
 * model: a new df_data_dict under the same df_meta is a partial update, and a
 * status other than "pending" is the end.
 *
 * A state change is a change to a dataflow field of buckaroo_state (the fields
 * the server reruns the dataflow for) and the frame that answers it carries the
 * next stats_gen. Either one starts the wait again with a delay, so a burst of
 * changes (typing in the search box) asks once, for the state it ends on. A
 * change to anything else, a search_string for one, leaves the schedule alone.
 *
 * `stats_gen` is the server's token for the state a reply describes. A reply for
 * another gen is dropped by StatsChannel, so no client-side token is kept here.
 */
import { BuckarooState, DFMeta } from "../components/WidgetTypes";
import { IModel } from "./IModel";

/** What the scheduler needs of a model. */
export type StatsModel = Pick<IModel, "get" | "on" | "off" | "send">;

/** The fields of buckaroo_state the server reruns the dataflow for, and so
 *  bumps stats_gen on. Mirrors _DATAFLOW_FIELDS in
 *  buckaroo/server/websocket_handler.py. */
export const DATAFLOW_STATE_FIELDS = ["post_processing", "cleaning_method", "quick_command_args"] as const;

/** Whether `next` differs from `prev` in a dataflow field. False when there is
 *  no earlier state to compare with. */
export function touchesDataflow(prev: BuckarooState | undefined, next: BuckarooState | undefined): boolean {
    if (prev === undefined || next === undefined) return false;
    return DATAFLOW_STATE_FIELDS.some((field) => JSON.stringify(prev[field]) !== JSON.stringify(next[field]));
}

/** The model key that holds the grid's column names currently on screen. */
export const VISIBLE_COLUMNS_KEY = "visible_columns";

/** Record the columns the grid shows, for the next `stats_request` to carry as
 *  its `columns` hint. An empty list means none are known. */
export function setVisibleColumns(model: Pick<IModel, "set">, columns: string[]): void {
    model.set(VISIBLE_COLUMNS_KEY, columns);
}

export interface StatsRequestOptions {
    /** Ask for stats the server did not plan to compute. The "Compute summary
     *  stats" control sends this. */
    force?: boolean;
}

/**
 * Send a time-boxed `stats_request` for the stats_gen of the state the model
 * shows, with the columns the grid shows as the hint when they are known.
 * Returns false, and sends nothing, when its df_meta carries no stats.gen.
 */
export function requestStats(model: Pick<IModel, "get" | "send">, opts: StatsRequestOptions = {}): boolean {
    const gen = (model.get("df_meta") as DFMeta | undefined)?.stats?.gen;
    if (typeof gen !== "number") return false;
    const columns = model.get(VISIBLE_COLUMNS_KEY) as string[] | undefined;
    model.send({
        type: "stats_request",
        stats_gen: gen,
        scope: "raw",
        incremental: true,
        ...(Array.isArray(columns) && columns.length > 0 ? { columns } : {}),
        ...(opts.force ? { force: true } : {}),
    });
    return true;
}

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

type Timer = ReturnType<typeof setTimeout>;

export class StateOrchestrator {
    private readonly model: StatsModel;
    private readonly minDebounceMs: number;
    private readonly maxDebounceMs: number;
    private readonly multiplier: number;
    private readonly initialRequestMs: number;
    private readonly firstPaintTimeoutMs: number;

    private started = false;
    // The stats_gen being driven; undefined while nothing is pending.
    private gen: number | undefined;
    // A request is out and its reply has not been seen.
    private inFlight = false;
    // Delay before the next request: 0 for the first state and for each reply
    // in a chain, the debounce after a state change.
    private delayMs = 0;
    // The state the model held at start has been read, so a pending state after
    // it is a state change, whatever the first one was.
    private began = false;
    private sentAt = 0;
    private lastRequestMs: number | undefined;
    private requestTimer: Timer | undefined;
    private paintTimer: Timer | undefined;
    private syncQueued = false;
    private seenMeta: unknown;
    private seenDict: unknown;
    private seenState: BuckarooState | undefined;

    constructor(opts: OrchestratorOptions) {
        this.model = opts.model;
        this.minDebounceMs = opts.minDebounceMs ?? 200;
        this.maxDebounceMs = opts.maxDebounceMs ?? 3000;
        this.multiplier = opts.multiplier ?? 2;
        this.initialRequestMs = opts.initialRequestMs ?? 250;
        this.firstPaintTimeoutMs = opts.firstPaintTimeoutMs ?? 1500;
    }

    /** Start watching the model, and adopt the state it already holds. */
    start(): void {
        if (this.started) return;
        this.started = true;
        this.seenMeta = this.model.get("df_meta");
        this.seenDict = this.model.get("df_data_dict");
        this.seenState = this.model.get("buckaroo_state");
        this.model.on("change:df_meta", this.onModelChange);
        this.model.on("change:df_data_dict", this.onModelChange);
        this.model.on("change:buckaroo_state", this.onState);
        this.model.on("msg:custom", this.onMessage);
        this.sync();
        this.began = true;
    }

    /** Stop watching and cancel anything scheduled. Call on unmount. */
    stop(): void {
        if (!this.started) return;
        this.started = false;
        this.model.off("change:df_meta", this.onModelChange);
        this.model.off("change:df_data_dict", this.onModelChange);
        this.model.off("change:buckaroo_state", this.onState);
        this.model.off("msg:custom", this.onMessage);
        this.standDown();
        this.began = false;
    }

    /**
     * The delay (ms) before asking for a new state's stats: the last observed
     * request time times the multiplier, clamped to
     * `[minDebounceMs, maxDebounceMs]`. A request that took longer means the
     * server was busy, so the next one waits longer.
     */
    computeDebounce(): number {
        const raw = (this.lastRequestMs ?? this.initialRequestMs) * this.multiplier;
        return Math.max(this.minDebounceMs, Math.min(this.maxDebounceMs, raw));
    }

    // A frame fires one change event per key, in the order the server wrote
    // them (df_data_dict before df_meta), so the model is read once they have
    // all landed, in a microtask, not at the first event.
    private readonly onModelChange = (): void => {
        if (this.syncQueued) return;
        this.syncQueued = true;
        void Promise.resolve().then(() => {
            this.syncQueued = false;
            if (this.started) this.sync();
        });
    };

    private readonly onState = (next?: BuckarooState): void => {
        const prev = this.seenState;
        this.seenState = next ?? this.model.get("buckaroo_state");
        if (this.gen === undefined || !touchesDataflow(prev, this.seenState)) return;
        this.begin(this.gen);
    };

    private readonly onMessage = (msg?: { type?: string }): void => {
        if (msg?.type === "infinite_resp") this.markPainted();
    };

    private sync(): void {
        const meta = this.model.get("df_meta") as DFMeta | undefined;
        const dict = this.model.get("df_data_dict");
        const metaChanged = meta !== this.seenMeta;
        const dictChanged = dict !== this.seenDict;
        this.seenMeta = meta;
        this.seenDict = dict;

        const stats = meta?.stats;
        if (stats?.status !== "pending" || typeof stats.gen !== "number") {
            // Complete, not computed, an error, or a server that reports no stats.
            this.standDown();
        } else if (stats.gen !== this.gen) {
            this.begin(stats.gen);
        } else if (this.inFlight && dictChanged && !metaChanged) {
            // A new df_data_dict under the same df_meta is a stats_update that
            // is not final (a full frame for this state replaces both). One
            // request per reply: ask again.
            this.inFlight = false;
            this.noteRequestTime();
            this.arm();
        }
    }

    // Wait for rows, then ask, for `gen`. The state the model starts with asks as
    // soon as rows are up; every later one is a state change and waits out the
    // debounce.
    private begin(gen: number): void {
        this.clearTimers();
        this.gen = gen;
        this.inFlight = false;
        this.delayMs = this.began ? this.computeDebounce() : 0;
        this.paintTimer = setTimeout(() => {
            this.paintTimer = undefined;
            this.markPainted();
        }, this.firstPaintTimeoutMs);
    }

    private standDown(): void {
        if (this.inFlight) this.noteRequestTime();
        this.clearTimers();
        this.gen = undefined;
        this.inFlight = false;
    }

    // The first rows are up (or the wait for them timed out): ask.
    private markPainted(): void {
        if (this.paintTimer !== undefined) {
            clearTimeout(this.paintTimer);
            this.paintTimer = undefined;
        }
        this.arm();
    }

    private arm(): void {
        if (this.inFlight || this.gen === undefined || this.requestTimer !== undefined) return;
        this.requestTimer = setTimeout(() => {
            this.requestTimer = undefined;
            this.fire();
        }, this.delayMs);
    }

    private fire(): void {
        if (requestStats(this.model)) {
            this.inFlight = true;
            this.sentAt = Date.now();
            this.delayMs = 0;
        }
    }

    private noteRequestTime(): void {
        this.lastRequestMs = Date.now() - this.sentAt;
    }

    private clearTimers(): void {
        if (this.requestTimer !== undefined) clearTimeout(this.requestTimer);
        if (this.paintTimer !== undefined) clearTimeout(this.paintTimer);
        this.requestTimer = undefined;
        this.paintTimer = undefined;
    }
}
