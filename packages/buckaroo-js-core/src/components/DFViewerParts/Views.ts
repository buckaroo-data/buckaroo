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


export class IdentityView implements View {
    private readonly _length: number;

    constructor(length: number) {
        this._length = length;
    }

    public length(): number {
        return this._length;
    }

    public positionAt(pos: number): number {
        return pos;
    }

    public rowidsInRange(start: number, end: number): number[] {
        const clampedEnd = Math.min(end, this._length);
        if (clampedEnd <= start) return [];
        const out: number[] = new Array(clampedEnd - start);
        for (let i = 0; i < out.length; i++) out[i] = start + i;
        return out;
    }

    public viewKey(): string {
        return "identity";
    }
}


export class SortView implements View {
    public readonly sortKey: string;
    public readonly sortDirection: SortDirection;
    public readonly rowidOrder: Int32Array;

    constructor(sortKey: string, sortDirection: SortDirection, rowidOrder: Int32Array) {
        this.sortKey = sortKey;
        this.sortDirection = sortDirection;
        this.rowidOrder = rowidOrder;
    }

    public length(): number {
        return this.rowidOrder.length;
    }

    public positionAt(pos: number): number {
        return this.rowidOrder[pos];
    }

    public rowidsInRange(start: number, end: number): number[] {
        const clampedEnd = Math.min(end, this.rowidOrder.length);
        if (clampedEnd <= start) return [];
        return Array.from(this.rowidOrder.subarray(start, clampedEnd));
    }

    public viewKey(): string {
        return `sort:${this.sortKey}:${this.sortDirection}`;
    }
}


export class FilterView implements View {
    public readonly filterKey: string;
    public readonly rowidSubset: Int32Array;

    constructor(filterKey: string, rowidSubset: Int32Array) {
        this.filterKey = filterKey;
        this.rowidSubset = rowidSubset;
    }

    public length(): number {
        return this.rowidSubset.length;
    }

    public positionAt(pos: number): number {
        return this.rowidSubset[pos];
    }

    public rowidsInRange(start: number, end: number): number[] {
        const clampedEnd = Math.min(end, this.rowidSubset.length);
        if (clampedEnd <= start) return [];
        return Array.from(this.rowidSubset.subarray(start, clampedEnd));
    }

    public viewKey(): string {
        return `filter:${this.filterKey}`;
    }
}
