import { DFData, DFDataOrPayload } from '../components/DFViewerParts/DFWhole';
import { IModel } from './IModel';
/** The capability this client advertises, as one value of `?caps=` on the
 *  WebSocket URL: it merges `stats_update` messages. The server records it per
 *  connection when the socket opens, since it sends the first message before
 *  the client can say anything. */
export declare const STATS_UPDATE_CAP = "stats_update";
/** `wsUrl` with `caps=stats_update` added: a new query on a bare URL, a new
 *  parameter after an existing query, or a comma-joined value when the host
 *  already passes `caps`. The fragment stays last and other parameters are
 *  left as the host wrote them. */
export declare function withStatsCapability(wsUrl: string): string;
export interface StatsUpdateMessage {
    type: "stats_update";
    stats_gen: number;
    scope?: string;
    tier?: string;
    final?: boolean;
    payload?: DFDataOrPayload;
    /** The display config the stats change (a float column's minWidth reads
     *  its min and max), present on a final update when it differs from the
     *  config the client was sent while the stats were pending. */
    df_display_args?: Record<string, unknown>;
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
export declare function mergeStatRows(base: DFData, update: DFData): DFData;
/** What the channel needs of a model. */
type StatsModel = Pick<IModel, "get" | "set">;
export declare class StatsChannel {
    private model;
    private applying;
    constructor(model: StatsModel);
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
    get expectedGen(): number | undefined;
    /** Consume a stats message. Returns false for every other message type,
     *  which the model handles (or ignores) as before. */
    handle(msg: {
        type?: string;
    }): boolean;
    private receiveUpdate;
    private applyUpdate;
    private receiveAborted;
    /** Replace `df_meta.stats` in a new `df_meta`, the reference that c0a's
     *  `inFlight` rule and the pinned rows' placeholders key on. */
    private replaceStats;
}
export {};
