/**
 * StatsChannel — the client half of the stats wire (rows-first c2).
 *
 * A client that advertises `?caps=stats_update` gets a first `initial_state`
 * whose `df_meta.stats` says the stats are pending, asks for them with
 * `stats_request {stats_gen, scope}`, and receives either
 *
 *   stats_update  {stats_gen, scope, tier, final, payload, elapsed_ms}
 *   stats_aborted {stats_gen, current_gen?, scope, reason}
 *
 * A final `stats_update` may also carry `status` and `reason` (rows-first c5):
 * `{final: true, status: "not_computed", reason: "ceiling"}`, with no payload,
 * answers a request the server refused, and the session is left in that state.
 * Without a `status` a final update completes the session. A run for some
 * columns ends the same way, with a payload, and the columns its replies filled
 * go in `df_meta.stats.computed_columns`, which the summary view reads to show
 * what the run computed.
 *
 * The server leaves `df_meta.stats.tier` where it was while a session is not
 * computed, so a run for the whole table that reached scalar shows nowhere in the
 * frame. The channel records it as `df_meta.stats.reached_tier` (rows-first c5b),
 * from the tier of the final reply. A reply does not say whether its run covered
 * the whole table or named columns, so the channel reads that from the
 * `stats_request` the client sent last, which `requestStats` records on the model
 * under STATS_REQUESTED_KEY.
 *
 * `payload` is an inline wide DFEnvelope holding `all_stats`. `stats_gen` is the
 * server's counter for the state the stats describe; it rides on every
 * `initial_state` as `df_meta.stats.gen`, and a reply for any other gen is for
 * a state the client has left. Sending the request is the scheduler's job, not
 * this module's.
 *
 * Merge semantics are WebSocket-only: `WebSocketModel` hands every frame to
 * `handle()` first, and Jupyter's widget sets `df_data_dict` whole.
 */
import { decodeDFData } from "../components/DFViewerParts/resolveDFData";
import { DFData, DFDataOrPayload } from "../components/DFViewerParts/DFWhole";
import { DFMeta, DFMetaStats, STATS_TIERS, StatsStatus, StatsTier, higherTier } from "../components/WidgetTypes";
import { IModel } from "./IModel";

/** A capability this client advertises, as one value of `?caps=` on the
 *  WebSocket URL: it merges `stats_update` messages. The server records it per
 *  connection when the socket opens, since it sends the first message before
 *  the client can say anything. */
export const STATS_UPDATE_CAP = "stats_update";

/** The second capability: this client can show a session whose stats are not
 *  computed, with the reason, and send tiered requests (see forceStats). A
 *  server applies its stats policy only to a client that has it. */
export const STATS_ONDEMAND_CAP = "stats_ondemand";

const CLIENT_CAPS = [STATS_UPDATE_CAP, STATS_ONDEMAND_CAP];

/** The model key under which requestStats records the `stats_request` it sent
 *  last. The channel reads it to tell a final reply to a run for the whole table
 *  (a tier and no columns) from one to a run for some columns. */
export const STATS_REQUESTED_KEY = "stats_requested";

/** What requestStats records under STATS_REQUESTED_KEY: the fields of the
 *  request that say what it was for. */
export interface StatsRequested {
    gen: number;
    tier?: string;
    columns?: string[];
}

const decodeQueryValue = (value: string): string => {
    try {
        return decodeURIComponent(value);
    } catch {
        return value;
    }
};

/** `wsUrl` with `caps=stats_update,stats_ondemand` added: a new query on a bare
 *  URL, a new parameter after an existing query, or a comma-joined value when
 *  the host already passes `caps`, to which only the capabilities it lacks are
 *  added. The fragment stays last and other parameters are left as the host
 *  wrote them. */
export function withStatsCapability(wsUrl: string): string {
    const hashAt = wsUrl.indexOf("#");
    const fragment = hashAt === -1 ? "" : wsUrl.slice(hashAt);
    const beforeFragment = hashAt === -1 ? wsUrl : wsUrl.slice(0, hashAt);
    const queryAt = beforeFragment.indexOf("?");
    const path = queryAt === -1 ? beforeFragment : beforeFragment.slice(0, queryAt);
    const params = queryAt === -1 ? [] : beforeFragment.slice(queryAt + 1).split("&").filter((p) => p !== "");

    const capsAt = params.findIndex((p) => p === "caps" || p.startsWith("caps="));
    if (capsAt === -1) {
        params.push(`caps=${CLIENT_CAPS.join(",")}`);
    } else {
        const caps = decodeQueryValue(params[capsAt].slice("caps=".length))
            .split(",")
            .map((cap) => cap.trim())
            .filter((cap) => cap !== "");
        for (const cap of CLIENT_CAPS) {
            if (!caps.includes(cap)) caps.push(cap);
        }
        params[capsAt] = `caps=${caps.join(",")}`;
    }
    return `${path}?${params.join("&")}${fragment}`;
}

export interface StatsUpdateMessage {
    type: "stats_update";
    stats_gen: number;
    scope?: string;
    tier?: string;
    final?: boolean;
    // A final reply that did not run, or ran for some columns only, says where
    // the stats stand. Absent means "complete".
    status?: StatsStatus;
    reason?: string;
    payload?: DFDataOrPayload;
    elapsed_ms?: number;
}

export interface StatsAbortedMessage {
    type: "stats_aborted";
    /** The request's gen. */
    stats_gen?: number;
    /** The session's gen, omitted when the session has no data. */
    current_gen?: number;
    scope?: string;
    reason?: "stale" | "unsupported_scope" | "not_requestable" | "error" | "no_data";
}

/**
 * Key-merge a stats payload into `all_stats`. Both are row-per-stat tables
 * (`{index: <stat>, <column>: <value>, ...}`). For each stat row the payload
 * names, every column it carries replaces that cell, columns it does not carry
 * keep theirs, and a stat the table lacks is appended.
 *
 * A `null` in the payload never replaces a value already merged: the wide
 * pivot fills a stat a column did not carry in this message with `null`.
 *
 * Returns new row objects and a new array. `base` may be the decoder's cached
 * array, so nothing in it is touched.
 */
export function mergeStatRows(base: DFData, update: DFData): DFData {
    const merged = base.slice();
    const at = new Map<unknown, number>();
    merged.forEach((row, i) => at.set(row.index, i));

    for (const updateRow of update) {
        const i = at.get(updateRow.index);
        if (i === undefined) {
            at.set(updateRow.index, merged.length);
            merged.push({ ...updateRow });
            continue;
        }
        const row = { ...merged[i] };
        for (const [column, value] of Object.entries(updateRow)) {
            if (column === "index" || column === "level_0") continue;
            if (value === null && row[column] != null) continue;
            row[column] = value;
        }
        merged[i] = row;
    }
    return merged;
}

const genOf = (meta: DFMeta | undefined): number | undefined => {
    const gen = meta?.stats?.gen;
    return typeof gen === "number" ? gen : undefined;
};

/** The columns of `rows` that hold a value in some stat row. The wide pivot
 *  fills a stat a column did not carry in a message with null, so a null says
 *  nothing about the column. */
function columnsWithValues(rows: DFData): string[] {
    const columns = new Set<string>();
    for (const row of rows) {
        for (const [column, value] of Object.entries(row)) {
            if (column !== "index" && column !== "level_0" && value != null) columns.add(column);
        }
    }
    return Array.from(columns);
}

/** `stats` with `columns` added to its `computed_columns`, or `stats` itself
 *  when there is nothing to add. */
function withComputedColumns(stats: DFMetaStats, columns: string[]): DFMetaStats {
    const all = Array.from(new Set([...(stats.computed_columns ?? []), ...columns]));
    return all.length === 0 ? stats : { ...stats, computed_columns: all };
}

/**
 * `df_meta.stats` after a final update. With no status it is complete at the
 * update's tier, and the policy fields, which only describe what is left to
 * ask for, go. With a status (a refusal, or a run for some columns only) the
 * session keeps its stats and takes the status and the reason, if the update
 * names one; the update's tier is what was asked for, not what was reached,
 * except where `reached` names the tier a run for the whole table reached (see
 * reachedBy), which goes in `reached_tier` when it is higher than the one there.
 * `filled` lists the columns the run's replies merged, and a session left not
 * computed adds them to `computed_columns`.
 */
function finalStats(
    stats: DFMetaStats,
    msg: StatsUpdateMessage,
    filled: string[],
    reached?: StatsTier,
): DFMetaStats {
    const status = msg.status ?? "complete";
    if (status === "complete") return { status, tier: msg.tier ?? stats.tier, gen: stats.gen };
    return withComputedColumns(
        {
            ...stats,
            status,
            ...(msg.reason === undefined ? {} : { reason: msg.reason }),
            ...(reached === undefined ? {} : { reached_tier: higherTier(stats.reached_tier, reached) }),
        },
        filled,
    );
}

/** What the channel needs of a model. */
type StatsModel = Pick<IModel, "get" | "set">;

export class StatsChannel {
    // Updates are applied one at a time: each reads the dict the previous one
    // wrote, so a later update cannot overwrite an earlier one's merge.
    private applying: Promise<void> = Promise.resolve();

    // The columns the replies of the run in progress filled, which its final
    // reply puts in df_meta.stats.computed_columns when it leaves the session
    // not computed. They are for one gen and for the df_data_dict this channel
    // last wrote: a new gen, or a frame that replaced the dict, took what the
    // run had merged, so the columns start over.
    private filled = new Set<string>();
    private filledGen: number | undefined;
    private filledDict: unknown;

    constructor(private model: StatsModel) {}

    /**
     * The stats_gen of the state the client is showing, or `undefined` when the
     * server reports none; a `stats_request` carries it. It is read off the
     * model's `df_meta` each time, so it starts from the frame the model was
     * built from and every applied `initial_state` (a broadcast frame with no
     * `reply_seq` included) moves it. A `df_meta` with no `stats.gen` leaves
     * nothing expected, so a server that stops reporting stats cannot have a
     * late `stats_update` merged. Reading the model, not the message, keeps this
     * correct under any scheme that drops stale `initial_state` frames.
     */
    get expectedGen(): number | undefined {
        return genOf(this.model.get("df_meta"));
    }

    /** Consume a stats message. Returns false for every other message type,
     *  which the model handles (or ignores) as before. */
    handle(msg: { type?: string }): boolean {
        if (msg.type === "stats_update") {
            this.receiveUpdate(msg as StatsUpdateMessage);
            return true;
        }
        if (msg.type === "stats_aborted") {
            this.receiveAborted(msg as StatsAbortedMessage);
            return true;
        }
        return false;
    }

    private receiveUpdate(msg: StatsUpdateMessage): void {
        if (msg.stats_gen !== this.expectedGen) return;
        this.applying = this.applying
            .then(() => this.applyUpdate(msg))
            .catch((e) => console.error("[StatsChannel] stats_update failed:", e));
    }

    private async applyUpdate(msg: StatsUpdateMessage): Promise<void> {
        // A reply that did not run (a request over the ceiling) has no payload
        // and nothing to merge.
        const update = msg.payload === undefined ? undefined : await decodeDFData(msg.payload);
        for (;;) {
            // A frame may have moved the gen on while something decoded.
            if (msg.stats_gen !== this.expectedGen) return;
            if (update !== undefined) {
                const dict: Record<string, DFDataOrPayload> | null | undefined = this.model.get("df_data_dict");
                // The dict is decoded when the seed built it and raw when a later
                // initial_state did.
                const base = await decodeDFData(dict?.all_stats);
                // A frame replaced the dict (or moved the gen) while it decoded:
                // start over from the new one.
                if (dict !== this.model.get("df_data_dict") || msg.stats_gen !== this.expectedGen) continue;
                this.model.set("df_data_dict", { ...dict, all_stats: mergeStatRows(base, update) });
                this.noteFilled(msg.stats_gen, dict, update);
            }
            if (msg.final) {
                const filled = this.takeFilled(msg.stats_gen);
                const reached = this.reachedBy(msg);
                this.replaceStats((stats) => finalStats(stats, msg, filled, reached));
            }
            return;
        }
    }

    private receiveAborted(msg: StatsAbortedMessage): void {
        // Only a reply to a request for the state on screen says anything about
        // it. A `stale` reply is answered by the initial_state that carries the
        // new gen; taking `current_gen` without that frame would merge stats
        // for a state the client has not seen into the one it shows.
        if (msg.stats_gen !== this.expectedGen) return;
        const filled = this.takeFilled(msg.stats_gen);
        if (msg.reason === "error") {
            this.replaceStats((stats) => ({ ...stats, status: "error", reason: "stats_failed" }));
        } else if (msg.reason === "not_requestable") {
            this.replaceStats((stats) => withComputedColumns({ ...stats, status: "not_computed" }, filled));
        }
    }

    /** The tier a final reply reached for the whole table, or undefined. The
     *  reply must have left the session not computed and carried a payload (a
     *  refusal, reason ceiling or cost, has none and names the tier that was
     *  asked for), and the request sent last must be for this gen and this tier
     *  with no columns: a tier with columns is a run for those columns. */
    private reachedBy(msg: StatsUpdateMessage): StatsTier | undefined {
        const tier = STATS_TIERS.find((t) => t === msg.tier);
        if (msg.status !== "not_computed" || msg.payload === undefined || tier === undefined) return undefined;
        const asked: StatsRequested | undefined = this.model.get(STATS_REQUESTED_KEY);
        const wholeTable = asked?.gen === msg.stats_gen && asked.tier === tier && asked.columns === undefined;
        return wholeTable ? tier : undefined;
    }

    /** Note the columns `update` filled in the dict this channel has just
     *  written over `before`. */
    private noteFilled(gen: number, before: unknown, update: DFData): void {
        if (this.filledGen !== gen || (this.filledDict !== undefined && this.filledDict !== before)) {
            this.filled = new Set();
        }
        this.filledGen = gen;
        for (const column of columnsWithValues(update)) this.filled.add(column);
        this.filledDict = this.model.get("df_data_dict");
    }

    /** The columns the run's replies filled, as of the reply that ends it:
     *  none when the gen or the dict has changed since. The next run starts
     *  from nothing. */
    private takeFilled(gen: number | undefined): string[] {
        const current = this.filledGen === gen && this.filledDict === this.model.get("df_data_dict");
        const columns = current ? Array.from(this.filled) : [];
        this.filled = new Set();
        this.filledGen = undefined;
        this.filledDict = undefined;
        return columns;
    }

    /** Replace `df_meta.stats` in a new `df_meta`, the reference that c0a's
     *  `inFlight` rule and the pinned rows' placeholders key on. */
    private replaceStats(change: (stats: DFMetaStats) => DFMetaStats): void {
        const meta: DFMeta | undefined = this.model.get("df_meta");
        if (!meta?.stats) return;
        this.model.set("df_meta", { ...meta, stats: change(meta.stats) });
    }
}
