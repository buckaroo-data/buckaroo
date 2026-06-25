import { DFDataRow } from './DFWhole';
import { RowCache, RowCacheConfig } from './RowCache';
import { SortDirection } from './Views';
/**
 * RowCacheController — the request/response lifecycle for the rowid-keyed
 * cache (see docs/smart-row-cache-redesign.md, phase 7b).
 *
 * This is the orchestration layer that `RowCache` (pure state) lacks: it
 * fires requests, parks the AG-Grid callback, replays it when the data
 * lands, dedupes in-flight work, and eagerly prefetches head/tail. It is
 * built net-new and runs PARALLEL to `KeyAwareSmartRowCache` — nothing is
 * cut over until the rowid system is ready to merge. It is JS-only and
 * fully testable against a mock `reqFn` (see RowCacheController.test.ts).
 *
 * One controller owns one generation (one `original_row_id` namespace).
 * The `Map<generationKey, RowCacheController>` wrapper is a follow-on
 * (see "Decisions resolved → the cache key is the generation").
 *
 * Lifecycle (reactive `drive()` loop):
 *   resolve the active view — if its permutation/subset isn't here yet, fire
 *   a `sort`/`filter` request and park (AG-Grid shows its loading overlay
 *   because we don't call the callback). Once built, `missingAt` the window;
 *   if present, resolve + `gc`; if not, fetch the missing rowids (by rowid,
 *   or positionally via `populate` for the identity view) and park. Every
 *   response re-drives all parked requests, so partial overlap and
 *   filter+sort composition fall out naturally.
 */
export type RowCacheReq = {
    kind: "sort";
    sourceName: string;
    sortKey: string;
    sortDirection: SortDirection;
} | {
    kind: "filter";
    sourceName: string;
    filterKey: string;
} | {
    kind: "rowsByRowid";
    sourceName: string;
    viewKey: string;
    rowids: number[];
} | {
    kind: "populate";
    sourceName: string;
    viewKey: string;
    start: number;
    end: number;
};
export type RowCacheResp = {
    kind: "sort";
    sourceName: string;
    sortKey: string;
    sortDirection: SortDirection;
    rowidOrder: Int32Array;
} | {
    kind: "filter";
    sourceName: string;
    filterKey: string;
    rowidSubset: Int32Array;
} | {
    kind: "rows";
    sourceName: string;
    viewKey: string;
    rowids: number[];
    rows: DFDataRow[];
};
export interface GridReq {
    sourceName: string;
    sort?: {
        sortKey: string;
        sortDirection: SortDirection;
    } | null;
    filterKey?: string | null;
    start: number;
    end: number;
}
export type SuccessCB = (rows: DFDataRow[], length: number) => void;
export type FailCB = () => void;
export type ReqFN = (req: RowCacheReq) => void;
export type RowCacheControllerConfig = RowCacheConfig & {
    sourceName: string;
};
export declare class RowCacheController {
    private readonly cache;
    private readonly reqFn;
    private readonly sourceName;
    private readonly headSize;
    private readonly tailSize;
    private pending;
    private readonly inFlightViews;
    private readonly inFlightFetches;
    constructor(reqFn: ReqFN, cfg: RowCacheControllerConfig);
    /** AG-Grid datasource entry point. Resolves async; `success` fires only
     * once the rows are present (loading overlay shows until then). */
    getRows(req: GridReq, success: SuccessCB, fail: FailCB): void;
    /** Feed a server response back in. */
    addResponse(resp: RowCacheResp): void;
    /** Server-side failure: fail every parked callback and reset in-flight. */
    addError(): void;
    pendingCount(): number;
    rowCache(): RowCache;
    private drive;
    /** Returns true if `p` was satisfied (success fired), false if parked. */
    private tryResolve;
    /** Resolve the view for a request; if a sort/filter permutation is not
     * built yet, fire the request(s) (deduped) and return undefined. */
    private resolveViewOrRequest;
    /** Filtered subset in sort order: the filtered rowids, ordered by the
     * sort permutation. Free because both are keyed off original_row_id. */
    private composeView;
    private requestSort;
    private requestFilter;
    private fetchMissing;
    /** Eagerly prefetch head/tail of a freshly-built view so the GC pin has
     * something to hold (the "second request" pattern). Fire-and-forget. */
    private eagerHeadTail;
    private sigForRows;
}
