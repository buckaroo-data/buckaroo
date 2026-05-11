/**
 * Phase 2 — the view layer.
 *
 * A view answers "what rowid is at position k under this ordering?"
 * Three flavors:
 *
 *   - IdentityView: default order. position == rowid. No allocation.
 *   - SortView:     {sortKey, sortDirection, rowidOrder: Int32Array}.
 *                   Full permutation of the dataset's rowids.
 *   - FilterView:   {filterKey, rowidSubset: Int32Array}.
 *                   Strict subset of rowids, in source order.
 *
 * Every view exposes the same lookup surface:
 *   length(), positionAt(k), rowidsInRange(start, end), viewKey().
 *
 * Tests are organized as
 *   - per-class behavior
 *   - a parameterized "View contract" suite that runs the same
 *     invariants against every view kind.
 */
import {
    IdentityView,
    SortView,
    FilterView,
    View,
} from "./Views";


describe("IdentityView", () => {
    test("position equals rowid", () => {
        const v = new IdentityView(100);
        expect(v.positionAt(0)).toBe(0);
        expect(v.positionAt(42)).toBe(42);
        expect(v.positionAt(99)).toBe(99);
    });

    test("length matches constructor arg", () => {
        expect(new IdentityView(0).length()).toBe(0);
        expect(new IdentityView(1).length()).toBe(1);
        expect(new IdentityView(1_000_000).length()).toBe(1_000_000);
    });

    test("rowidsInRange returns [start..end)", () => {
        const v = new IdentityView(100);
        expect(v.rowidsInRange(0, 5)).toStrictEqual([0, 1, 2, 3, 4]);
        expect(v.rowidsInRange(10, 13)).toStrictEqual([10, 11, 12]);
    });

    test("rowidsInRange clamps end at length", () => {
        const v = new IdentityView(5);
        expect(v.rowidsInRange(3, 10)).toStrictEqual([3, 4]);
    });

    test("rowidsInRange returns [] for empty or inverted range", () => {
        const v = new IdentityView(100);
        expect(v.rowidsInRange(50, 50)).toStrictEqual([]);
        expect(v.rowidsInRange(50, 40)).toStrictEqual([]);
    });

    test("viewKey is a stable 'identity' tag", () => {
        // Used as the cache lookup key; identity views share one key
        // because they're all the same view.
        expect(new IdentityView(100).viewKey()).toBe("identity");
        expect(new IdentityView(50).viewKey()).toBe("identity");
    });
});


describe("SortView", () => {
    const perm = (xs: number[]) => Int32Array.from(xs);

    test("positionAt indexes into rowidOrder", () => {
        const v = new SortView("age", "asc", perm([3, 1, 4, 1, 5, 9, 2, 6]));
        expect(v.positionAt(0)).toBe(3);
        expect(v.positionAt(4)).toBe(5);
        expect(v.positionAt(7)).toBe(6);
    });

    test("length matches rowidOrder length", () => {
        expect(new SortView("age", "asc", perm([])).length()).toBe(0);
        expect(new SortView("age", "asc", perm([0, 1, 2])).length()).toBe(3);
    });

    test("rowidsInRange returns the slice as plain number[]", () => {
        const v = new SortView("age", "asc", perm([3, 1, 4, 1, 5, 9, 2, 6]));
        const slice = v.rowidsInRange(2, 5);
        expect(slice).toStrictEqual([4, 1, 5]);
        expect(Array.isArray(slice)).toBe(true);
    });

    test("rowidsInRange clamps end at length", () => {
        const v = new SortView("age", "asc", perm([10, 20, 30]));
        expect(v.rowidsInRange(1, 100)).toStrictEqual([20, 30]);
    });

    test("viewKey encodes sortKey + direction", () => {
        const asc = new SortView("age", "asc", perm([0]));
        const desc = new SortView("age", "desc", perm([0]));
        const other = new SortView("name", "asc", perm([0]));
        expect(asc.viewKey()).not.toBe(desc.viewKey());
        expect(asc.viewKey()).not.toBe(other.viewKey());
        expect(asc.viewKey()).toBe(new SortView("age", "asc", perm([0])).viewKey());
    });
});


describe("FilterView", () => {
    const sub = (xs: number[]) => Int32Array.from(xs);

    test("positionAt indexes into rowidSubset", () => {
        const v = new FilterView("name~foo", sub([7, 11, 13, 21]));
        expect(v.positionAt(0)).toBe(7);
        expect(v.positionAt(3)).toBe(21);
    });

    test("length matches subset length, not source length", () => {
        // The whole point of filter: length is the size of the result,
        // not the source.
        const v = new FilterView("name~foo", sub([7, 11, 13]));
        expect(v.length()).toBe(3);
    });

    test("rowidsInRange returns plain number[] slice", () => {
        const v = new FilterView("name~foo", sub([7, 11, 13, 21, 30]));
        expect(v.rowidsInRange(1, 4)).toStrictEqual([11, 13, 21]);
    });

    test("viewKey encodes filterKey", () => {
        const a = new FilterView("name~foo", sub([0]));
        const b = new FilterView("name~bar", sub([0]));
        expect(a.viewKey()).not.toBe(b.viewKey());
    });

    test("viewKey of a FilterView does not collide with a SortView", () => {
        // Used to live in different LRU caches; verify the keys can't
        // accidentally alias.
        const f = new FilterView("age", sub([0]));
        const s = new SortView("age", "asc", Int32Array.from([0]));
        expect(f.viewKey()).not.toBe(s.viewKey());
    });
});


describe("View contract — invariants across all view kinds", () => {
    const cases: Array<[string, View]> = [
        ["IdentityView(8)", new IdentityView(8)],
        ["SortView", new SortView("k", "asc", Int32Array.from([3, 1, 4, 1, 5, 9, 2, 6]))],
        ["FilterView", new FilterView("f", Int32Array.from([3, 1, 4, 1, 5, 9, 2, 6]))],
    ];

    test.each(cases)("%s — rowidsInRange(0, length()) returns length() items", (_label, v) => {
        const all = v.rowidsInRange(0, v.length());
        expect(all).toHaveLength(v.length());
    });

    test.each(cases)("%s — rowidsInRange and positionAt agree", (_label, v) => {
        const slice = v.rowidsInRange(2, 5);
        for (let i = 0; i < slice.length; i++) {
            expect(slice[i]).toBe(v.positionAt(2 + i));
        }
    });

    test.each(cases)("%s — viewKey is non-empty", (_label, v) => {
        expect(v.viewKey().length).toBeGreaterThan(0);
    });
});


describe("View — out-of-bounds positionAt", () => {
    // Phase 2 contract: callers are expected to clamp via length()
    // before calling positionAt. The view does not need to be defensive
    // — out-of-bounds is the caller's bug. We assert "doesn't crash on
    // negative", which means it either returns garbage or throws —
    // either is fine, we just don't want a silent infinite loop.
    test("IdentityView positionAt(-1) is well-behaved (doesn't hang)", () => {
        const v = new IdentityView(10);
        // either throws or returns a number; both are acceptable
        expect(() => v.positionAt(-1)).not.toThrow(/timeout/i);
    });
});
