import { DFData, DFDataOrPayload } from '../components/DFViewerParts/DFWhole';
import { StatsStatus } from '../components/WidgetTypes';
import { IModel } from './IModel';
/** A capability this client advertises, as one value of `?caps=` on the
 *  WebSocket URL: it merges `stats_update` messages. The server records it per
 *  connection when the socket opens, since it sends the first message before
 *  the client can say anything. */
export declare const STATS_UPDATE_CAP = "stats_update";
/** The second capability: this client can show a session whose stats are not
 *  computed, with the reason, and send tiered requests (see forceStats). A
 *  server applies its stats policy only to a client that has it. */
export declare const STATS_ONDEMAND_CAP = "stats_ondemand";
/** The model key under which requestStats records the `stats_request` it sent
 *  last. The channel reads it to tell a final reply to a run for the whole table
 *  (a tier and no columns) from one to a run for some columns. */
export declare const STATS_REQUESTED_KEY = "stats_requested";
/** What requestStats records under STATS_REQUESTED_KEY: the fields of the
 *  request that say what it was for. */
export interface StatsRequested {
    gen: number;
    tier?: string;
    columns?: string[];
}
/** `wsUrl` with `caps=stats_update,stats_ondemand` added: a new query on a bare
 *  URL, a new parameter after an existing query, or a comma-joined value when
 *  the host already passes `caps`, to which only the capabilities it lacks are
 *  added. The fragment stays last and other parameters are left as the host
 *  wrote them. */
export declare function withStatsCapability(wsUrl: string): string;
export interface StatsUpdateMessage {
    type: "stats_update";
    stats_gen: number;
    scope?: string;
    tier?: string;
    final?: boolean;
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
export declare function mergeStatRows(base: DFData, update: DFData): DFData;
/** What the channel needs of a model. */
type StatsModel = Pick<IModel, "get" | "set">;
export declare class StatsChannel {
    private model;
    private applying;
    private filled;
    private filledGen;
    private filledDict;
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
    /** The tier a final reply reached for the whole table, or undefined. The
     *  reply must have left the session not computed and carried a payload (a
     *  refusal, reason ceiling or cost, has none and names the tier that was
     *  asked for), and the request sent last must be for this gen and this tier
     *  with no columns: a tier with columns is a run for those columns. */
    private reachedBy;
    /** Note the columns `update` filled in the dict this channel has just
     *  written over `before`. */
    private noteFilled;
    /** The columns the run's replies filled, as of the reply that ends it:
     *  none when the gen or the dict has changed since. The next run starts
     *  from nothing. */
    private takeFilled;
    /** Replace `df_meta.stats` in a new `df_meta`, the reference that c0a's
     *  `inFlight` rule and the pinned rows' placeholders key on. */
    private replaceStats;
}
export {};
