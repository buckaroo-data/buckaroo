import { DFDataRow } from "./DFWhole";
import { RowCache, RowCacheConfig } from "./RowCache";
import {
    View,
    SortView,
    FilterView,
    SortDirection,
    sortViewKey,
    filterViewKey,
    IDENTITY_VIEW_KEY,
} from "./Views";

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

export type RowCacheReq =
    | { kind: "sort"; sourceName: string; sortKey: string; sortDirection: SortDirection }
    | { kind: "filter"; sourceName: string; filterKey: string }
    | { kind: "rowsByRowid"; sourceName: string; viewKey: string; rowids: number[] }
    | { kind: "populate"; sourceName: string; viewKey: string; start: number; end: number };

export type RowCacheResp =
    | { kind: "sort"; sourceName: string; sortKey: string; sortDirection: SortDirection; rowidOrder: Int32Array }
    | { kind: "filter"; sourceName: string; filterKey: string; rowidSubset: Int32Array }
    | { kind: "rows"; sourceName: string; viewKey: string; rowids: number[]; rows: DFDataRow[] };

export interface GridReq {
    sourceName: string;
    sort?: { sortKey: string; sortDirection: SortDirection } | null;
    filterKey?: string | null;
    start: number;
    end: number;
}

export type SuccessCB = (rows: DFDataRow[], length: number) => void;
export type FailCB = () => void;
export type ReqFN = (req: RowCacheReq) => void;

export type RowCacheControllerConfig = RowCacheConfig & { sourceName: string };

interface Pending {
    req: GridReq;
    success: SuccessCB;
    fail: FailCB;
}


export class RowCacheController {
    private readonly cache: RowCache;
    private readonly reqFn: ReqFN;
    private readonly sourceName: string;
    private readonly headSize: number;
    private readonly tailSize: number;

    private pending: Pending[] = [];
    // viewKeys of sort/filter permutations currently being fetched
    private readonly inFlightViews = new Set<string>();
    // signatures of row fetches currently outstanding
    private readonly inFlightFetches = new Set<string>();

    constructor(reqFn: ReqFN, cfg: RowCacheControllerConfig) {
        this.reqFn = reqFn;
        this.sourceName = cfg.sourceName;
        this.cache = new RowCache(cfg);
        const resolved = this.cache.config();
        this.headSize = resolved.headSize;
        this.tailSize = resolved.tailSize;
    }

    /** AG-Grid datasource entry point. Resolves async; `success` fires only
     * once the rows are present (loading overlay shows until then). */
    public getRows(req: GridReq, success: SuccessCB, fail: FailCB): void {
        this.pending.push({ req, success, fail });
        this.drive();
    }

    /** Feed a server response back in. */
    public addResponse(resp: RowCacheResp): void {
        if (resp.kind === "sort") {
            const view = this.cache.applySort({
                sortKey: resp.sortKey,
                sortDirection: resp.sortDirection,
                rowidOrder: resp.rowidOrder,
            });
            this.inFlightViews.delete(sortViewKey(resp.sortKey, resp.sortDirection));
            this.drive();
            this.eagerHeadTail(view);
        } else if (resp.kind === "filter") {
            this.cache.applyFilter({ filterKey: resp.filterKey, rowidSubset: resp.rowidSubset });
            this.inFlightViews.delete(filterViewKey(resp.filterKey));
            this.drive();
        } else {
            // Assumes the response carries every requested rowid (complete).
            this.cache.populate({ rowids: resp.rowids, rows: resp.rows });
            this.inFlightFetches.delete(this.sigForRows(resp.viewKey, resp.rowids));
            this.drive();
        }
    }

    /** Server-side failure: fail every parked callback and reset in-flight. */
    public addError(): void {
        const parked = this.pending;
        this.pending = [];
        this.inFlightViews.clear();
        this.inFlightFetches.clear();
        for (const p of parked) p.fail();
    }

    public pendingCount(): number {
        return this.pending.length;
    }

    public rowCache(): RowCache {
        return this.cache;
    }

    // ---- internals -------------------------------------------------------

    private drive(): void {
        const still: Pending[] = [];
        for (const p of this.pending) {
            if (!this.tryResolve(p)) still.push(p);
        }
        this.pending = still;
    }

    /** Returns true if `p` was satisfied (success fired), false if parked. */
    private tryResolve(p: Pending): boolean {
        const view = this.resolveViewOrRequest(p.req);
        if (view === undefined) return false;
        const { start, end } = p.req;
        const missing = this.cache.missingAt(view, start, end);
        if (missing.length === 0) {
            const rows = this.cache.rowsAt(view, start, end) as DFDataRow[];
            p.success(rows, view.length());
            this.cache.gc({ view, start, end });
            return true;
        }
        this.fetchMissing(view, start, end, missing);
        return false;
    }

    /** Resolve the view for a request; if a sort/filter permutation is not
     * built yet, fire the request(s) (deduped) and return undefined. */
    private resolveViewOrRequest(req: GridReq): View | undefined {
        const hasSort = req.sort !== undefined && req.sort !== null;
        const hasFilter = req.filterKey !== undefined && req.filterKey !== null;
        if (!hasSort && !hasFilter) return this.cache.defaultView();

        let sortView: SortView | undefined;
        let filterView: FilterView | undefined;
        if (hasSort) {
            sortView = this.cache.getSortView(req.sort!.sortKey, req.sort!.sortDirection);
            if (sortView === undefined) this.requestSort(req.sort!.sortKey, req.sort!.sortDirection);
        }
        if (hasFilter) {
            filterView = this.cache.getFilterView(req.filterKey!);
            if (filterView === undefined) this.requestFilter(req.filterKey!);
        }
        if (hasSort && hasFilter) {
            if (sortView !== undefined && filterView !== undefined) {
                return this.composeView(sortView, filterView);
            }
            return undefined;
        }
        return hasSort ? sortView : filterView;
    }

    /** Filtered subset in sort order: the filtered rowids, ordered by the
     * sort permutation. Free because both are keyed off original_row_id. */
    private composeView(s: SortView, f: FilterView): FilterView {
        const subset = new Set<number>();
        for (let i = 0; i < f.rowidSubset.length; i++) subset.add(f.rowidSubset[i]);
        const out: number[] = [];
        for (let i = 0; i < s.rowidOrder.length; i++) {
            const r = s.rowidOrder[i];
            if (subset.has(r)) out.push(r);
        }
        return new FilterView(`${s.viewKey()}&${f.viewKey()}`, Int32Array.from(out));
    }

    private requestSort(sortKey: string, sortDirection: SortDirection): void {
        const vk = sortViewKey(sortKey, sortDirection);
        if (this.inFlightViews.has(vk)) return;
        this.inFlightViews.add(vk);
        this.reqFn({ kind: "sort", sourceName: this.sourceName, sortKey, sortDirection });
    }

    private requestFilter(filterKey: string): void {
        const vk = filterViewKey(filterKey);
        if (this.inFlightViews.has(vk)) return;
        this.inFlightViews.add(vk);
        this.reqFn({ kind: "filter", sourceName: this.sourceName, filterKey });
    }

    private fetchMissing(view: View, start: number, end: number, missing: number[]): void {
        const vk = view.viewKey();
        if (vk === IDENTITY_VIEW_KEY) {
            // identity is positional: fetch the whole window via populate
            const windowRowids = view.rowidsInRange(start, end);
            const sig = this.sigForRows(vk, windowRowids);
            if (this.inFlightFetches.has(sig)) return;
            this.inFlightFetches.add(sig);
            this.reqFn({ kind: "populate", sourceName: this.sourceName, viewKey: vk, start, end });
        } else {
            // non-identity: fetch only the missing rowids by id
            const sig = this.sigForRows(vk, missing);
            if (this.inFlightFetches.has(sig)) return;
            this.inFlightFetches.add(sig);
            this.reqFn({ kind: "rowsByRowid", sourceName: this.sourceName, viewKey: vk, rowids: missing });
        }
    }

    /** Eagerly prefetch head/tail of a freshly-built view so the GC pin has
     * something to hold (the "second request" pattern). Fire-and-forget. */
    private eagerHeadTail(view: View): void {
        const len = view.length();
        const windows: Array<[number, number]> = [];
        if (this.headSize > 0) windows.push([0, Math.min(this.headSize, len)]);
        if (this.tailSize > 0) windows.push([Math.max(0, len - this.tailSize), len]);
        for (const [s, e] of windows) {
            if (e <= s) continue;
            const missing = this.cache.missingAt(view, s, e);
            if (missing.length === 0) continue;
            this.fetchMissing(view, s, e, missing);
        }
    }

    private sigForRows(viewKey: string, rowids: number[] | Int32Array): string {
        const arr = Array.from(rowids).sort((a, b) => a - b);
        return `${viewKey}:${arr.join(",")}`;
    }
}
