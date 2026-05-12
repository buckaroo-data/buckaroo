import { DFDataRow } from './DFWhole';
import { View, IdentityView, SortView, FilterView, SortDirection } from './Views';
import { ActiveWindow } from './RowStoreGc';
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
export declare class RowCache {
    private readonly cfg;
    private readonly rowStore;
    private readonly sortRegistry;
    private readonly filterRegistry;
    private readonly _defaultView;
    constructor(cfg: RowCacheConfig);
    config(): ResolvedConfig;
    defaultView(): IdentityView;
    rowStoreSize(): number;
    has(rowid: number): boolean;
    populate(input: PopulateInput): void;
    applySort(input: SortInput): SortView;
    applyFilter(input: FilterInput): FilterView;
    getSortView(sortKey: string, sortDirection: SortDirection): SortView | undefined;
    getFilterView(filterKey: string): FilterView | undefined;
    rowsAt(view: View, start: number, end: number): (DFDataRow | undefined)[];
    missingAt(view: View, start: number, end: number): number[];
    gc(activeWindow: ActiveWindow): void;
}
export {};
