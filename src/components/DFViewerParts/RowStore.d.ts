import { DFDataRow } from './DFWhole';
/**
 * Rowid-keyed store of row contents. The only place row data lives in
 * the redesigned cache (see docs/smart-row-cache-redesign.md).
 *
 * Rowids are stable identifiers assigned by the server at initial
 * population — they survive sort and filter, so a single RowStore can
 * back any number of SortViews and FilterViews. Visibility-aware GC
 * and head/tail pinning live in `RowStoreGc.ts`.
 */
export declare class RowStore {
    private rows;
    set(rowid: number, row: DFDataRow): void;
    setMany(rowids: number[], rows: DFDataRow[]): void;
    get(rowid: number): DFDataRow | undefined;
    getMany(rowids: number[]): (DFDataRow | undefined)[];
    has(rowid: number): boolean;
    delete(rowid: number): void;
    size(): number;
    rowids(): IterableIterator<number>;
    missingRowids(rowids: number[]): number[];
}
