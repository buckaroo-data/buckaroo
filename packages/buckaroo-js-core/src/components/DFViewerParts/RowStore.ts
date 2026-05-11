import { DFDataRow } from "./DFWhole";


/**
 * Rowid-keyed store of row contents. The only place row data lives in
 * the redesigned cache (see docs/smart-row-cache-redesign.md).
 *
 * Rowids are stable identifiers assigned by the server at initial
 * population — they survive sort and filter, so a single RowStore can
 * back any number of SortViews and FilterViews.
 *
 * This class is intentionally tiny in phase 1. GC and pinning land in
 * later phases.
 */
export class RowStore {
    private rows: Map<number, DFDataRow> = new Map();

    public set(rowid: number, row: DFDataRow): void {
        this.rows.set(rowid, row);
    }

    public setMany(rowids: number[], rows: DFDataRow[]): void {
        if (rowids.length !== rows.length) {
            throw new Error(
                `RowStore.setMany: rowids.length=${rowids.length} !== rows.length=${rows.length}`,
            );
        }
        for (let i = 0; i < rowids.length; i++) {
            this.rows.set(rowids[i], rows[i]);
        }
    }

    public get(rowid: number): DFDataRow | undefined {
        return this.rows.get(rowid);
    }

    public getMany(rowids: number[]): (DFDataRow | undefined)[] {
        return rowids.map((r) => this.rows.get(r));
    }

    public has(rowid: number): boolean {
        return this.rows.has(rowid);
    }

    public delete(rowid: number): void {
        this.rows.delete(rowid);
    }

    public size(): number {
        return this.rows.size;
    }

    public rowids(): IterableIterator<number> {
        return this.rows.keys();
    }

    public missingRowids(rowids: number[]): number[] {
        const seen = new Set<number>();
        const out: number[] = [];
        for (const r of rowids) {
            if (seen.has(r)) continue;
            seen.add(r);
            if (!this.rows.has(r)) out.push(r);
        }
        return out;
    }
}
