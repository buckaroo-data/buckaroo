/**
 * Phase 1 — basic Map-like surface keyed by rowid.
 *
 * GC, pinning, and view-aware eviction land in later phases and are
 * deliberately not exercised here.
 */
import { DFDataRow } from "./DFWhole";
import { RowStore } from "./RowStore";


const row = (n: number): DFDataRow => ({ a: n, b: `name_${n}` });


describe("RowStore — basic API", () => {
    test("an empty store has size 0 and has() returns false", () => {
        const rs = new RowStore();
        expect(rs.size()).toBe(0);
        expect(rs.has(0)).toBe(false);
        expect(rs.has(1234)).toBe(false);
    });

    test("set + get round-trips a row", () => {
        const rs = new RowStore();
        rs.set(7, row(7));
        expect(rs.has(7)).toBe(true);
        expect(rs.get(7)).toStrictEqual(row(7));
        expect(rs.size()).toBe(1);
    });

    test("get of an unknown rowid returns undefined", () => {
        const rs = new RowStore();
        rs.set(1, row(1));
        expect(rs.get(999)).toBeUndefined();
    });

    test("set on an existing rowid overwrites", () => {
        const rs = new RowStore();
        rs.set(3, row(3));
        rs.set(3, { ...row(3), b: "renamed" });
        expect(rs.get(3)).toStrictEqual({ a: 3, b: "renamed" });
        expect(rs.size()).toBe(1);
    });

    test("delete removes a rowid", () => {
        const rs = new RowStore();
        rs.set(5, row(5));
        expect(rs.has(5)).toBe(true);
        rs.delete(5);
        expect(rs.has(5)).toBe(false);
        expect(rs.get(5)).toBeUndefined();
        expect(rs.size()).toBe(0);
    });

    test("delete of an unknown rowid is a no-op", () => {
        const rs = new RowStore();
        rs.set(5, row(5));
        rs.delete(999);
        expect(rs.size()).toBe(1);
        expect(rs.has(5)).toBe(true);
    });
});


describe("RowStore — bulk operations", () => {
    test("setMany stores paired rowids and rows", () => {
        const rs = new RowStore();
        const rowids = [10, 11, 12];
        const rows = [row(10), row(11), row(12)];
        rs.setMany(rowids, rows);
        expect(rs.size()).toBe(3);
        for (const r of rowids) {
            expect(rs.get(r)).toStrictEqual(row(r));
        }
    });

    test("setMany throws when arrays have different lengths", () => {
        const rs = new RowStore();
        expect(() => rs.setMany([1, 2], [row(1)])).toThrow();
    });

    test("setMany on overlapping rowids overwrites in place", () => {
        const rs = new RowStore();
        rs.set(10, row(10));
        rs.setMany([10, 11], [{ a: 10, b: "updated" }, row(11)]);
        expect(rs.size()).toBe(2);
        expect(rs.get(10)).toStrictEqual({ a: 10, b: "updated" });
        expect(rs.get(11)).toStrictEqual(row(11));
    });

    test("getMany returns rows in input order", () => {
        const rs = new RowStore();
        rs.setMany([10, 11, 12], [row(10), row(11), row(12)]);
        expect(rs.getMany([12, 10, 11])).toStrictEqual([
            row(12),
            row(10),
            row(11),
        ]);
    });

    test("getMany returns undefined for missing rowids", () => {
        const rs = new RowStore();
        rs.set(10, row(10));
        expect(rs.getMany([10, 999, 11])).toStrictEqual([
            row(10),
            undefined,
            undefined,
        ]);
    });

    test("getMany on empty input returns empty array", () => {
        const rs = new RowStore();
        rs.set(10, row(10));
        expect(rs.getMany([])).toStrictEqual([]);
    });
});


describe("RowStore — missingRowids", () => {
    // Used by the view layer to figure out which rowids it has to ask
    // the server for after a position-range lookup hits some uncached
    // slots. Trivial wrapper over has(), but the call site is hot
    // enough that it's worth a method.
    test("missingRowids returns rowids not present, preserving input order", () => {
        const rs = new RowStore();
        rs.setMany([10, 12], [row(10), row(12)]);
        expect(rs.missingRowids([10, 11, 12, 13])).toStrictEqual([11, 13]);
    });

    test("missingRowids on an empty store returns the input unchanged", () => {
        const rs = new RowStore();
        expect(rs.missingRowids([1, 2, 3])).toStrictEqual([1, 2, 3]);
    });

    test("missingRowids deduplicates", () => {
        const rs = new RowStore();
        rs.set(5, row(5));
        expect(rs.missingRowids([5, 6, 6, 7, 7])).toStrictEqual([6, 7]);
    });
});
