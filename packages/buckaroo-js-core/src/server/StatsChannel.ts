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
import { DFMeta, DFMetaStats, StatsStatus } from "../components/WidgetTypes";
import { IModel } from "./IModel";

/** The capability this client advertises, as one value of `?caps=` on the
 *  WebSocket URL: it merges `stats_update` messages. The server records it per
 *  connection when the socket opens, since it sends the first message before
 *  the client can say anything. */
export const STATS_UPDATE_CAP = "stats_update";

const decodeQueryValue = (value: string): string => {
    try {
        return decodeURIComponent(value);
    } catch {
        return value;
    }
};

/** `wsUrl` with `caps=stats_update` added: a new query on a bare URL, a new
 *  parameter after an existing query, or a comma-joined value when the host
 *  already passes `caps`. The fragment stays last and other parameters are
 *  left as the host wrote them. */
export function withStatsCapability(wsUrl: string): string {
    const hashAt = wsUrl.indexOf("#");
    const fragment = hashAt === -1 ? "" : wsUrl.slice(hashAt);
    const beforeFragment = hashAt === -1 ? wsUrl : wsUrl.slice(0, hashAt);
    const queryAt = beforeFragment.indexOf("?");
    const path = queryAt === -1 ? beforeFragment : beforeFragment.slice(0, queryAt);
    const params = queryAt === -1 ? [] : beforeFragment.slice(queryAt + 1).split("&").filter((p) => p !== "");

    const capsAt = params.findIndex((p) => p === "caps" || p.startsWith("caps="));
    if (capsAt === -1) {
        params.push(`caps=${STATS_UPDATE_CAP}`);
    } else {
        const caps = decodeQueryValue(params[capsAt].slice("caps=".length))
            .split(",")
            .map((cap) => cap.trim())
            .filter((cap) => cap !== "");
        if (!caps.includes(STATS_UPDATE_CAP)) caps.push(STATS_UPDATE_CAP);
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

/** What the channel needs of a model. */
type StatsModel = Pick<IModel, "get" | "set">;

export class StatsChannel {
    // Updates are applied one at a time: each reads the dict the previous one
    // wrote, so a later update cannot overwrite an earlier one's merge.
    private applying: Promise<void> = Promise.resolve();

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
        const update = await decodeDFData(msg.payload);
        for (;;) {
            // A frame may have moved the gen on while something decoded.
            if (msg.stats_gen !== this.expectedGen) return;
            const dict: Record<string, DFDataOrPayload> | null | undefined = this.model.get("df_data_dict");
            // The dict is decoded when the seed built it and raw when a later
            // initial_state did.
            const base = await decodeDFData(dict?.all_stats);
            // A frame replaced the dict (or moved the gen) while it decoded:
            // start over from the new one.
            if (dict !== this.model.get("df_data_dict") || msg.stats_gen !== this.expectedGen) continue;
            this.model.set("df_data_dict", { ...dict, all_stats: mergeStatRows(base, update) });
            if (msg.final) {
                this.replaceStats((stats) => ({ status: "complete", tier: msg.tier ?? stats.tier, gen: stats.gen }));
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
        if (msg.reason === "error") {
            this.replaceStats((stats) => ({ ...stats, status: "error", reason: "stats_failed" }));
        } else if (msg.reason === "not_requestable") {
            this.replaceStats((stats) => ({ ...stats, status: "not_computed" }));
        }
    }

    /** Replace `df_meta.stats` in a new `df_meta`, the reference that c0a's
     *  `inFlight` rule and the pinned rows' placeholders key on. */
    private replaceStats(change: (stats: DFMetaStats) => DFMetaStats): void {
        const meta: DFMeta | undefined = this.model.get("df_meta");
        if (!meta?.stats) return;
        this.model.set("df_meta", { ...meta, stats: change(meta.stats) });
    }
}
