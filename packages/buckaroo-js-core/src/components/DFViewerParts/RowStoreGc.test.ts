/**
 * Phase 3 — visibility-aware GC for RowStore.
 *
 * "Active window" = a position range within a view. To decide which
 * rowids are still needed, the GC takes every active window, expands
 * by padding, maps positions → rowids through each window's view, and
 * keeps the union. Everything else is dropped.
 *
 * No knowledge of head/tail pinning yet — that's phase 4.
 */
import { RowStore } from "./RowStore";
import { IdentityView, SortView, FilterView, View } from "./Views";
import { gcRowStore, ActiveWindow } from "./RowStoreGc";


function fillStore(rs: RowStore, rowids: number[]): void {
    rs.setMany(
        rowids,
        rowids.map((r) => ({ a: r })),
    );
}

function aw(view: View, start: number, end: number): ActiveWindow {
    return { view, start, end };
}


describe("gcRowStore — identity view", () => {
    test("keeps only rowids inside the visible window ± padding", () => {
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);

        gcRowStore(rs, [aw(new IdentityView(10), 3, 6)], 1);

        // window [3, 6) ± 1 ⇒ keep rowids [2, 3, 4, 5, 6]
        for (const r of [2, 3, 4, 5, 6]) expect(rs.has(r)).toBe(true);
        for (const r of [0, 1, 7, 8, 9]) expect(rs.has(r)).toBe(false);
    });

    test("zero padding keeps exactly the window", () => {
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2, 3, 4]);
        gcRowStore(rs, [aw(new IdentityView(5), 1, 4)], 0);
        expect(rs.size()).toBe(3);
        expect(rs.has(0)).toBe(false);
        expect(rs.has(1)).toBe(true);
        expect(rs.has(3)).toBe(true);
        expect(rs.has(4)).toBe(false);
    });

    test("padding doesn't extend below 0 or beyond view length", () => {
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2, 3, 4]);
        gcRowStore(rs, [aw(new IdentityView(5), 0, 5)], 100);
        // window covers everything, padding can't add more
        for (const r of [0, 1, 2, 3, 4]) expect(rs.has(r)).toBe(true);
    });
});


describe("gcRowStore — sort view", () => {
    test("keeps the rowids at the visible positions under the sort", () => {
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);

        // sort: positions [0..10) → rowids [3, 1, 4, 1, 5, 9, 2, 6, 5, 0]
        const order = Int32Array.from([3, 1, 4, 1, 5, 9, 2, 6, 5, 0]);
        const sv = new SortView("k", "asc", order);

        // visible window [2, 5) under sort ⇒ positions 2,3,4 ⇒ rowids 4, 1, 5
        gcRowStore(rs, [aw(sv, 2, 5)], 0);

        for (const r of [1, 4, 5]) expect(rs.has(r)).toBe(true);
        for (const r of [0, 2, 3, 6, 7, 8, 9]) expect(rs.has(r)).toBe(false);
    });

    test("padding works in position-space, not rowid-space", () => {
        const rs = new RowStore();
        fillStore(rs, [10, 20, 30, 40, 50]);

        const order = Int32Array.from([30, 10, 50, 20, 40]);
        const sv = new SortView("k", "asc", order);

        // window [2, 3) ± 1 ⇒ positions [1, 4) ⇒ rowids 10, 50, 20
        gcRowStore(rs, [aw(sv, 2, 3)], 1);

        expect(rs.has(10)).toBe(true);
        expect(rs.has(20)).toBe(true);
        expect(rs.has(50)).toBe(true);
        expect(rs.has(30)).toBe(false);
        expect(rs.has(40)).toBe(false);
    });
});


describe("gcRowStore — multiple views", () => {
    test("keeps the union of rowids across all active windows", () => {
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);

        const idv = new IdentityView(10);
        // sort: pos 0..10 → rowids [7, 6, 5, 4, 3, 2, 1, 0, 9, 8]
        const sv = new SortView("k", "desc", Int32Array.from([7, 6, 5, 4, 3, 2, 1, 0, 9, 8]));

        // identity window [0, 2) ⇒ rowids 0, 1
        // sort window [0, 2) ⇒ rowids 7, 6
        gcRowStore(rs, [aw(idv, 0, 2), aw(sv, 0, 2)], 0);

        for (const r of [0, 1, 6, 7]) expect(rs.has(r)).toBe(true);
        for (const r of [2, 3, 4, 5, 8, 9]) expect(rs.has(r)).toBe(false);
    });

    test("filter and sort window unions are tracked separately", () => {
        const rs = new RowStore();
        fillStore(rs, [10, 20, 30, 40, 50, 60, 70, 80, 90]);

        const fv = new FilterView("active", Int32Array.from([20, 40, 60, 80]));
        const sv = new SortView("k", "asc", Int32Array.from([90, 80, 70, 60, 50, 40, 30, 20, 10]));

        // filter window [0, 2) ⇒ rowids 20, 40
        // sort window   [0, 1) ⇒ rowids 90
        gcRowStore(rs, [aw(fv, 0, 2), aw(sv, 0, 1)], 0);

        for (const r of [20, 40, 90]) expect(rs.has(r)).toBe(true);
        for (const r of [10, 30, 50, 60, 70, 80]) expect(rs.has(r)).toBe(false);
    });
});


describe("gcRowStore — edge cases", () => {
    test("empty active-windows list drops everything", () => {
        const rs = new RowStore();
        fillStore(rs, [1, 2, 3]);
        gcRowStore(rs, [], 5);
        expect(rs.size()).toBe(0);
    });

    test("does not touch rowids not in any window's reach (still in store)", () => {
        // Verify gcRowStore only deletes from RowStore, doesn't create
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2]);
        const before = rs.size();
        gcRowStore(rs, [aw(new IdentityView(10), 0, 3)], 0);
        expect(rs.size()).toBe(before);
    });

    test("a rowid in the keep set but missing from the store is a no-op", () => {
        // Keep set asks for rowid 99, store doesn't have it — no error.
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2]);
        gcRowStore(rs, [aw(new IdentityView(100), 0, 100)], 0);
        // Nothing weird happens; the rowids it did have survive.
        expect(rs.size()).toBe(3);
    });

    test("window with start >= end is treated as empty", () => {
        const rs = new RowStore();
        fillStore(rs, [0, 1, 2]);
        gcRowStore(rs, [aw(new IdentityView(10), 5, 5)], 0);
        expect(rs.size()).toBe(0);
    });
});
