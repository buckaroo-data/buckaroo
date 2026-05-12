/**
 * View layer: "what rowid is at position k under this ordering?"
 *
 * The RowStore holds row contents keyed by rowid; views answer the
 * complementary question of which rowid lives where. The renderer
 * composes:
 *
 *   view V at position k  →  rowid r = V.positionAt(k)  →  RowStore.get(r)
 *
 * Three kinds, all answering the same contract:
 *   - IdentityView: position == rowid. No backing array.
 *   - SortView:     wraps an Int32Array permutation of the dataset.
 *   - FilterView:   wraps an Int32Array subset of the dataset.
 *
 * See docs/smart-row-cache-redesign.md.
 */
export type SortDirection = "asc" | "desc";
export interface View {
    length(): number;
    positionAt(pos: number): number;
    rowidsInRange(start: number, end: number): number[];
    viewKey(): string;
}
export declare class IdentityView implements View {
    private readonly _length;
    constructor(length: number);
    length(): number;
    positionAt(pos: number): number;
    rowidsInRange(start: number, end: number): number[];
    viewKey(): string;
}
export declare class SortView implements View {
    readonly sortKey: string;
    readonly sortDirection: SortDirection;
    readonly rowidOrder: Int32Array;
    constructor(sortKey: string, sortDirection: SortDirection, rowidOrder: Int32Array);
    length(): number;
    positionAt(pos: number): number;
    rowidsInRange(start: number, end: number): number[];
    viewKey(): string;
}
export declare class FilterView implements View {
    readonly filterKey: string;
    readonly rowidSubset: Int32Array;
    constructor(filterKey: string, rowidSubset: Int32Array);
    length(): number;
    positionAt(pos: number): number;
    rowidsInRange(start: number, end: number): number[];
    viewKey(): string;
}
