import { DFDataRow } from "./DFWhole";
import { RowStore } from "./RowStore";
import {
    View,
    IdentityView,
    SortView,
    FilterView,
    SortDirection,
    sortViewKey,
    filterViewKey,
} from "./Views";
import { ViewRegistry } from "./ViewRegistry";
import { gcRowStore, ActiveWindow, PinSpec } from "./RowStoreGc";


export interface RowCacheConfig {
    datasetLength: number;
    padding?: number;
    headSize?: number;
    tailSize?: number;
    sortCapacity?: number;
    filterCapacity?: number;
}


interface ResolvedConfig {
    datasetLength: number;
    padding: number;
    headSize: number;
    tailSize: number;
    sortCapacity: number;
    filterCapacity: number;
}


function resolveConfig(c: RowCacheConfig): ResolvedConfig {
    return {
        datasetLength: c.datasetLength,
        padding: c.padding ?? 200,
        headSize: c.headSize ?? 20,
        tailSize: c.tailSize ?? 20,
        sortCapacity: c.sortCapacity ?? 4,
        filterCapacity: c.filterCapacity ?? 4,
    };
}


export interface PopulateInput {
    rowids: number[];
    rows: DFDataRow[];
}


export interface SortInput {
    sortKey: string;
    sortDirection: SortDirection;
    rowidOrder: Int32Array;
}


export interface FilterInput {
    filterKey: string;
    rowidSubset: Int32Array;
}


/**
 * Controller that integrates RowStore + ViewRegistry + gcRowStore.
 *
 * This is the API the widget consumer talks to. Network plumbing and
 * AG-Grid wiring live outside; the controller is pure state.
 *
 * The default view is IdentityView(datasetLength) — no allocation.
 */
export class RowCache {
    private readonly cfg: ResolvedConfig;
    private readonly rowStore: RowStore = new RowStore();
    private readonly sortRegistry: ViewRegistry;
    private readonly filterRegistry: ViewRegistry;
    private readonly _defaultView: IdentityView;

    constructor(cfg: RowCacheConfig) {
        this.cfg = resolveConfig(cfg);
        this.sortRegistry = new ViewRegistry(this.cfg.sortCapacity);
        this.filterRegistry = new ViewRegistry(this.cfg.filterCapacity);
        this._defaultView = new IdentityView(this.cfg.datasetLength);
    }

    public config(): ResolvedConfig {
        return this.cfg;
    }

    public defaultView(): IdentityView {
        return this._defaultView;
    }

    public rowStoreSize(): number {
        return this.rowStore.size();
    }

    public has(rowid: number): boolean {
        return this.rowStore.has(rowid);
    }

    public populate(input: PopulateInput): void {
        this.rowStore.setMany(input.rowids, input.rows);
    }

    public applySort(input: SortInput): SortView {
        const view = new SortView(input.sortKey, input.sortDirection, input.rowidOrder);
        this.sortRegistry.add(view);
        return view;
    }

    public applyFilter(input: FilterInput): FilterView {
        const view = new FilterView(input.filterKey, input.rowidSubset);
        this.filterRegistry.add(view);
        return view;
    }

    public getSortView(sortKey: string, sortDirection: SortDirection): SortView | undefined {
        const v = this.sortRegistry.get(sortViewKey(sortKey, sortDirection));
        return v as SortView | undefined;
    }

    public getFilterView(filterKey: string): FilterView | undefined {
        const v = this.filterRegistry.get(filterViewKey(filterKey));
        return v as FilterView | undefined;
    }

    public rowsAt(view: View, start: number, end: number): (DFDataRow | undefined)[] {
        const rowids = view.rowidsInRange(start, end);
        return this.rowStore.getMany(rowids);
    }

    public missingAt(view: View, start: number, end: number): number[] {
        const rowids = view.rowidsInRange(start, end);
        return this.rowStore.missingRowids(rowids);
    }

    public gc(activeWindow: ActiveWindow): void {
        const pinnedViews: View[] = [this._defaultView];
        for (const k of this.sortRegistry.keys()) {
            const v = this.sortRegistry.get(k);
            if (v !== undefined) pinnedViews.push(v);
        }
        for (const k of this.filterRegistry.keys()) {
            const v = this.filterRegistry.get(k);
            if (v !== undefined) pinnedViews.push(v);
        }
        const pin: PinSpec = {
            views: pinnedViews,
            headSize: this.cfg.headSize,
            tailSize: this.cfg.tailSize,
        };
        gcRowStore(this.rowStore, [activeWindow], this.cfg.padding, pin);
    }
}
