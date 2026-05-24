/**
 * Phase 7 — the RowCache controller.
 *
 * Integrates the four pieces from phases 1-5 into a single API that
 * the widget consumer will use:
 *
 *   - RowStore: rowid → row contents
 *   - ViewRegistry × 2: SortViews + FilterViews (each LRU-4)
 *   - gcRowStore + PinSpec for visibility-aware + head/tail GC
 *
 * Surface:
 *   - populate({rowids, rows})        — server populate response
 *   - applySort({sortKey, dir, order}) — server sort response
 *   - applyFilter({key, subset})       — server filter response
 *   - rowsAt(view, start, end)         — what the renderer needs
 *   - missingAt(view, start, end)      — what to ask the server for
 *   - gc(activeWindow)                 — trim around current viewport
 *
 * No network/widget plumbing here — pure controller logic.
 */
import { RowCache } from "./RowCache";
import { SortView, FilterView, IdentityView } from "./Views";


describe("RowCache — populate", () => {
    test("populate stores rows under their rowids", () => {
        const c = new RowCache({ datasetLength: 10 });
        c.populate({
            rowids: [0, 1, 2],
            rows: [{ a: 0 }, { a: 1 }, { a: 2 }],
        });
        expect(c.rowStoreSize()).toBe(3);
    });

    test("repeated populate of the same rowid overwrites", () => {
        const c = new RowCache({ datasetLength: 10 });
        c.populate({ rowids: [0], rows: [{ a: 0 }] });
        c.populate({ rowids: [0], rows: [{ a: "updated" }] });
        expect(c.rowStoreSize()).toBe(1);
    });
});


describe("RowCache — default identity view", () => {
    test("rowsAt without an active view uses the identity view", () => {
        const c = new RowCache({ datasetLength: 10 });
        c.populate({ rowids: [0, 1, 2], rows: [{ a: 0 }, { a: 1 }, { a: 2 }] });
        const view = c.defaultView();
        expect(view).toBeInstanceOf(IdentityView);
        expect(view.length()).toBe(10);

        const rows = c.rowsAt(view, 0, 3);
        expect(rows).toStrictEqual([{ a: 0 }, { a: 1 }, { a: 2 }]);
    });

    test("rowsAt for a window with missing rowids returns undefined for gaps", () => {
        const c = new RowCache({ datasetLength: 10 });
        c.populate({ rowids: [0, 2], rows: [{ a: 0 }, { a: 2 }] });
        const rows = c.rowsAt(c.defaultView(), 0, 3);
        expect(rows).toStrictEqual([{ a: 0 }, undefined, { a: 2 }]);
    });

    test("missingAt enumerates uncached rowids in a window", () => {
        const c = new RowCache({ datasetLength: 10 });
        c.populate({ rowids: [0, 2], rows: [{ a: 0 }, { a: 2 }] });
        expect(c.missingAt(c.defaultView(), 0, 3)).toStrictEqual([1]);
    });
});


describe("RowCache — sort", () => {
    test("applySort registers the SortView and rowsAt resolves through it", () => {
        const c = new RowCache({ datasetLength: 5 });
        c.populate({
            rowids: [0, 1, 2, 3, 4],
            rows: [
                { a: 0, age: 30 },
                { a: 1, age: 25 },
                { a: 2, age: 40 },
                { a: 3, age: 35 },
                { a: 4, age: 28 },
            ],
        });

        // sort by age asc → rowids: 1, 4, 0, 3, 2
        c.applySort({
            sortKey: "age",
            sortDirection: "asc",
            rowidOrder: Int32Array.from([1, 4, 0, 3, 2]),
        });

        const sv = c.getSortView("age", "asc")!;
        expect(sv).toBeInstanceOf(SortView);

        const rows = c.rowsAt(sv, 0, 3);
        // position 0,1,2 → rowids 1, 4, 0 → ages 25, 28, 30
        expect(rows!.map((r) => r && (r as any).age)).toStrictEqual([25, 28, 30]);
    });

    test("after a sort, the rows under the sort are reused — no row refetch needed", () => {
        const c = new RowCache({ datasetLength: 5 });
        c.populate({
            rowids: [0, 1, 2, 3, 4],
            rows: [
                { a: 0 },
                { a: 1 },
                { a: 2 },
                { a: 3 },
                { a: 4 },
            ],
        });
        c.applySort({
            sortKey: "k",
            sortDirection: "asc",
            rowidOrder: Int32Array.from([4, 3, 2, 1, 0]),
        });
        const sv = c.getSortView("k", "asc")!;
        // Every rowid is already cached — missingAt is empty.
        expect(c.missingAt(sv, 0, 5)).toStrictEqual([]);
        expect(c.rowsAt(sv, 0, 5)).toStrictEqual([
            { a: 4 },
            { a: 3 },
            { a: 2 },
            { a: 1 },
            { a: 0 },
        ]);
    });

    test("two sorts coexist — neither refetches rows", () => {
        const c = new RowCache({ datasetLength: 3 });
        c.populate({
            rowids: [0, 1, 2],
            rows: [{ a: 10 }, { a: 20 }, { a: 30 }],
        });
        c.applySort({
            sortKey: "k1",
            sortDirection: "asc",
            rowidOrder: Int32Array.from([2, 1, 0]),
        });
        c.applySort({
            sortKey: "k2",
            sortDirection: "desc",
            rowidOrder: Int32Array.from([0, 2, 1]),
        });
        const s1 = c.getSortView("k1", "asc")!;
        const s2 = c.getSortView("k2", "desc")!;

        expect(c.missingAt(s1, 0, 3)).toStrictEqual([]);
        expect(c.missingAt(s2, 0, 3)).toStrictEqual([]);
    });
});


describe("RowCache — filter", () => {
    test("applyFilter registers a FilterView and rowsAt resolves through it", () => {
        const c = new RowCache({ datasetLength: 5 });
        c.populate({
            rowids: [0, 1, 2, 3, 4],
            rows: [
                { a: 0, name: "foo" },
                { a: 1, name: "bar" },
                { a: 2, name: "foo" },
                { a: 3, name: "baz" },
                { a: 4, name: "foo" },
            ],
        });
        c.applyFilter({
            filterKey: "name~foo",
            rowidSubset: Int32Array.from([0, 2, 4]),
        });
        const fv = c.getFilterView("name~foo")!;
        expect(fv).toBeInstanceOf(FilterView);
        expect(fv.length()).toBe(3);

        const rows = c.rowsAt(fv, 0, 3);
        expect(rows!.map((r) => r && (r as any).a)).toStrictEqual([0, 2, 4]);
    });
});


describe("RowCache — view LRU", () => {
    test("the sort view registry evicts at capacity", () => {
        const c = new RowCache({ datasetLength: 1, sortCapacity: 2 });
        c.applySort({ sortKey: "a", sortDirection: "asc", rowidOrder: Int32Array.from([0]) });
        c.applySort({ sortKey: "b", sortDirection: "asc", rowidOrder: Int32Array.from([0]) });
        c.applySort({ sortKey: "c", sortDirection: "asc", rowidOrder: Int32Array.from([0]) });
        expect(c.getSortView("a", "asc")).toBeUndefined();
        expect(c.getSortView("b", "asc")).toBeDefined();
        expect(c.getSortView("c", "asc")).toBeDefined();
    });

    test("the filter view registry evicts at capacity", () => {
        const c = new RowCache({ datasetLength: 1, filterCapacity: 2 });
        c.applyFilter({ filterKey: "a", rowidSubset: Int32Array.from([0]) });
        c.applyFilter({ filterKey: "b", rowidSubset: Int32Array.from([0]) });
        c.applyFilter({ filterKey: "c", rowidSubset: Int32Array.from([0]) });
        expect(c.getFilterView("a")).toBeUndefined();
        expect(c.getFilterView("b")).toBeDefined();
        expect(c.getFilterView("c")).toBeDefined();
    });
});


describe("RowCache — GC", () => {
    test("gc() drops rowids far from the active window, keeping pinned head/tail", () => {
        const c = new RowCache({
            datasetLength: 20,
            padding: 2,
            headSize: 2,
            tailSize: 2,
        });
        // populate everything
        c.populate({
            rowids: Array.from({ length: 20 }, (_, i) => i),
            rows: Array.from({ length: 20 }, (_, i) => ({ a: i })),
        });
        // active window in the middle of the identity view
        c.gc({ view: c.defaultView(), start: 8, end: 11 });

        // visibility window: positions 6..13 ⇒ rowids 6..12
        // head: rowids 0, 1
        // tail: rowids 18, 19
        for (const r of [0, 1, 6, 7, 8, 9, 10, 11, 12, 18, 19]) {
            expect(c.has(r)).toBe(true);
        }
        for (const r of [2, 3, 4, 5, 13, 14, 15, 16, 17]) {
            expect(c.has(r)).toBe(false);
        }
    });

    test("gc pins head/tail of every active SortView too", () => {
        const c = new RowCache({
            datasetLength: 10,
            padding: 0,
            headSize: 2,
            tailSize: 0,
        });
        c.populate({
            rowids: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
            rows: Array.from({ length: 10 }, (_, i) => ({ a: i })),
        });
        // sort: rowids reverse
        c.applySort({
            sortKey: "k",
            sortDirection: "asc",
            rowidOrder: Int32Array.from([9, 8, 7, 6, 5, 4, 3, 2, 1, 0]),
        });
        const sv = c.getSortView("k", "asc")!;

        // active window on the sort, deep in the middle
        c.gc({ view: sv, start: 4, end: 6 });

        // identity head: rowids 0, 1
        // sort head:     rowids 9, 8
        // window pos 4..6 in sort → rowids 5, 4
        for (const r of [0, 1, 4, 5, 8, 9]) expect(c.has(r)).toBe(true);
        for (const r of [2, 3, 6, 7]) expect(c.has(r)).toBe(false);
    });
});


describe("RowCache — defaults", () => {
    test("the default config picks sensible padding / head / tail", () => {
        const c = new RowCache({ datasetLength: 100 });
        const cfg = c.config();
        // Just assert these are positive — the exact numbers should
        // be tunable, but never zero.
        expect(cfg.padding).toBeGreaterThan(0);
        expect(cfg.headSize).toBeGreaterThan(0);
        expect(cfg.tailSize).toBeGreaterThan(0);
        expect(cfg.sortCapacity).toBeGreaterThanOrEqual(1);
        expect(cfg.filterCapacity).toBeGreaterThanOrEqual(1);
    });
});
