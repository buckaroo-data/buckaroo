/**
 * RowCacheController — the request/response lifecycle for the rowid-keyed
 * cache. This is the JS-only orchestration layer (parallel to
 * KeyAwareSmartRowCache; no cutover yet). These tests drive it against a
 * mock reqFn that records outgoing requests; the test then feeds responses
 * back in via addResponse to simulate the server.
 *
 * Lifecycle decisions encoded here:
 *   - loading overlay during a gap = the success callback is NOT fired until
 *     rows are actually present
 *   - sort is two round-trips (sort -> rowidOrder -> rows), where the view
 *     does not exist until the permutation lands
 *   - an in-flight sort/filter is deduped; a second viewport request attaches
 *   - after a sort lands, head/tail are eagerly prefetched (the "second
 *     request" pattern)
 *   - filter + sort compose client-side (filtered subset in sort order)
 *   - rows under a non-identity view are fetched by rowid (only the missing
 *     ones); the identity view fetches its window positionally via populate
 */
import { RowCacheController, RowCacheReq } from "./RowCacheController";
import { DFDataRow } from "./DFWhole";

const rowsFor = (rowids: number[]): DFDataRow[] =>
    rowids.map((r) => ({ a: r, label: `row-${r}` } as unknown as DFDataRow));

const aOf = (rows: DFDataRow[]): number[] => rows.map((r) => (r as unknown as { a: number }).a);

function harness(opts: {
    datasetLength: number;
    headSize?: number;
    tailSize?: number;
    sortCapacity?: number;
}) {
    const sent: RowCacheReq[] = [];
    const reqFn = (r: RowCacheReq) => sent.push(r);
    const ctl = new RowCacheController(reqFn, {
        sourceName: "s",
        datasetLength: opts.datasetLength,
        headSize: opts.headSize ?? 20,
        tailSize: opts.tailSize ?? 20,
        sortCapacity: opts.sortCapacity ?? 4,
    });
    const byKind = (k: string) => sent.filter((r) => r.kind === k);
    return { sent, ctl, byKind };
}

const ident = (n: number) => Int32Array.from(Array.from({ length: n }, (_, i) => i));


describe("RowCacheController — identity view", () => {
    test("cold: parks the callback, fires a populate, resolves on the rows response", () => {
        const { sent, ctl } = harness({ datasetLength: 100 });
        const success = jest.fn();
        const fail = jest.fn();
        ctl.getRows({ sourceName: "s", start: 0, end: 5 }, success, fail);

        // loading overlay: nothing resolved yet
        expect(success).not.toHaveBeenCalled();
        expect(sent).toEqual([
            { kind: "populate", sourceName: "s", viewKey: "identity", start: 0, end: 5 },
        ]);

        ctl.addResponse({
            kind: "rows",
            sourceName: "s",
            viewKey: "identity",
            rowids: [0, 1, 2, 3, 4],
            rows: rowsFor([0, 1, 2, 3, 4]),
        });

        expect(success).toHaveBeenCalledTimes(1);
        expect(aOf(success.mock.calls[0][0])).toEqual([0, 1, 2, 3, 4]);
        expect(success.mock.calls[0][1]).toBe(100);
    });

    test("warm: a cached window resolves synchronously with no new request", () => {
        const { sent, ctl } = harness({ datasetLength: 100 });
        ctl.getRows({ sourceName: "s", start: 0, end: 5 }, jest.fn(), jest.fn());
        ctl.addResponse({
            kind: "rows",
            sourceName: "s",
            viewKey: "identity",
            rowids: [0, 1, 2, 3, 4],
            rows: rowsFor([0, 1, 2, 3, 4]),
        });
        const before = sent.length;

        const success = jest.fn();
        ctl.getRows({ sourceName: "s", start: 0, end: 5 }, success, jest.fn());
        expect(success).toHaveBeenCalledTimes(1);
        expect(sent.length).toBe(before);
    });
});


describe("RowCacheController — sort lifecycle", () => {
    test("two round-trips: sort -> rowidOrder -> rowsByRowid -> rows, in sort order", () => {
        const { sent, ctl } = harness({ datasetLength: 5, headSize: 0, tailSize: 0 });
        const success = jest.fn();
        ctl.getRows(
            { sourceName: "s", sort: { sortKey: "age", sortDirection: "asc" }, start: 0, end: 3 },
            success,
            jest.fn(),
        );

        // first hop: a sort request only, no rows, no resolution
        expect(success).not.toHaveBeenCalled();
        expect(sent).toEqual([
            { kind: "sort", sourceName: "s", sortKey: "age", sortDirection: "asc" },
        ]);

        ctl.addResponse({
            kind: "sort",
            sourceName: "s",
            sortKey: "age",
            sortDirection: "asc",
            rowidOrder: Int32Array.from([4, 3, 2, 1, 0]),
        });

        // second hop: fetch the window's rowids by id; still no resolution
        const rowsReq = sent.find((r) => r.kind === "rowsByRowid");
        expect(rowsReq).toBeDefined();
        expect((rowsReq as { rowids: number[] }).rowids).toEqual([4, 3, 2]);
        expect(success).not.toHaveBeenCalled();

        ctl.addResponse({
            kind: "rows",
            sourceName: "s",
            viewKey: "sort:age:asc",
            rowids: [4, 3, 2],
            rows: rowsFor([4, 3, 2]),
        });

        expect(success).toHaveBeenCalledTimes(1);
        expect(aOf(success.mock.calls[0][0])).toEqual([4, 3, 2]);
        expect(success.mock.calls[0][1]).toBe(5);
    });

    test("dedupe: two viewport requests for the same unbuilt sort fire one sort request", () => {
        const { ctl, byKind } = harness({ datasetLength: 10, headSize: 0, tailSize: 0 });
        const s1 = jest.fn();
        const s2 = jest.fn();
        ctl.getRows({ sourceName: "s", sort: { sortKey: "age", sortDirection: "asc" }, start: 0, end: 3 }, s1, jest.fn());
        ctl.getRows({ sourceName: "s", sort: { sortKey: "age", sortDirection: "asc" }, start: 3, end: 6 }, s2, jest.fn());

        expect(byKind("sort").length).toBe(1);

        ctl.addResponse({
            kind: "sort", sourceName: "s", sortKey: "age", sortDirection: "asc",
            rowidOrder: ident(10),
        });
        expect(byKind("rowsByRowid").length).toBe(2);

        ctl.addResponse({ kind: "rows", sourceName: "s", viewKey: "sort:age:asc", rowids: [0, 1, 2], rows: rowsFor([0, 1, 2]) });
        ctl.addResponse({ kind: "rows", sourceName: "s", viewKey: "sort:age:asc", rowids: [3, 4, 5], rows: rowsFor([3, 4, 5]) });
        expect(s1).toHaveBeenCalledTimes(1);
        expect(s2).toHaveBeenCalledTimes(1);
    });

    test("eager head/tail: after a sort lands, head and tail windows are prefetched", () => {
        const { ctl, byKind } = harness({ datasetLength: 1000, headSize: 20, tailSize: 20 });
        ctl.getRows(
            { sourceName: "s", sort: { sortKey: "age", sortDirection: "asc" }, start: 500, end: 520 },
            jest.fn(),
            jest.fn(),
        );
        ctl.addResponse({
            kind: "sort", sourceName: "s", sortKey: "age", sortDirection: "asc",
            rowidOrder: ident(1000),
        });

        const fetches = byKind("rowsByRowid") as Array<{ rowids: number[] }>;
        expect(fetches.some((r) => r.rowids[0] === 500)).toBe(true); // the visible window
        expect(fetches.some((r) => r.rowids[0] === 0)).toBe(true); // head
        expect(fetches.some((r) => r.rowids[r.rowids.length - 1] === 999)).toBe(true); // tail
    });

    test("scrolling under a built sort fetches only the missing rowids by id", () => {
        const { sent, ctl } = harness({ datasetLength: 10, headSize: 0, tailSize: 0 });
        ctl.getRows({ sourceName: "s", sort: { sortKey: "k", sortDirection: "asc" }, start: 0, end: 3 }, jest.fn(), jest.fn());
        ctl.addResponse({ kind: "sort", sourceName: "s", sortKey: "k", sortDirection: "asc", rowidOrder: ident(10) });
        ctl.addResponse({ kind: "rows", sourceName: "s", viewKey: "sort:k:asc", rowids: [0, 1, 2], rows: rowsFor([0, 1, 2]) });

        const success = jest.fn();
        ctl.getRows({ sourceName: "s", sort: { sortKey: "k", sortDirection: "asc" }, start: 2, end: 5 }, success, jest.fn());

        const last = sent[sent.length - 1] as { kind: string; rowids: number[] };
        expect(last.kind).toBe("rowsByRowid");
        expect(last.rowids).toEqual([3, 4]); // 2 was already cached

        ctl.addResponse({ kind: "rows", sourceName: "s", viewKey: "sort:k:asc", rowids: [3, 4], rows: rowsFor([3, 4]) });
        expect(success).toHaveBeenCalledTimes(1);
        expect(aOf(success.mock.calls[0][0])).toEqual([2, 3, 4]);
    });
});


describe("RowCacheController — filter and composition", () => {
    test("filter: builds the FilterView then fetches the subset rows", () => {
        const { sent, ctl } = harness({ datasetLength: 100, headSize: 0, tailSize: 0 });
        const success = jest.fn();
        ctl.getRows({ sourceName: "s", filterKey: "age>50", start: 0, end: 3 }, success, jest.fn());

        expect(sent).toEqual([{ kind: "filter", sourceName: "s", filterKey: "age>50" }]);

        ctl.addResponse({ kind: "filter", sourceName: "s", filterKey: "age>50", rowidSubset: Int32Array.from([10, 20, 30, 40]) });
        const rowsReq = sent.find((r) => r.kind === "rowsByRowid") as { rowids: number[] };
        expect(rowsReq.rowids).toEqual([10, 20, 30]);

        ctl.addResponse({ kind: "rows", sourceName: "s", viewKey: "filter:age>50", rowids: [10, 20, 30], rows: rowsFor([10, 20, 30]) });
        expect(success).toHaveBeenCalledTimes(1);
        expect(aOf(success.mock.calls[0][0])).toEqual([10, 20, 30]);
        expect(success.mock.calls[0][1]).toBe(4); // filter length, not dataset length
    });

    test("filter + sort compose client-side: filtered subset in sort order, fetched by rowid", () => {
        const { sent, ctl, byKind } = harness({ datasetLength: 10, headSize: 0, tailSize: 0 });
        const success = jest.fn();
        ctl.getRows(
            { sourceName: "s", sort: { sortKey: "age", sortDirection: "desc" }, filterKey: "even", start: 0, end: 3 },
            success,
            jest.fn(),
        );
        expect(byKind("sort").length).toBe(1);
        expect(byKind("filter").length).toBe(1);
        expect(success).not.toHaveBeenCalled();

        // descending order over 0..9
        ctl.addResponse({ kind: "sort", sourceName: "s", sortKey: "age", sortDirection: "desc", rowidOrder: Int32Array.from([9, 8, 7, 6, 5, 4, 3, 2, 1, 0]) });
        // evens, arbitrary order
        ctl.addResponse({ kind: "filter", sourceName: "s", filterKey: "even", rowidSubset: Int32Array.from([0, 2, 4, 6, 8]) });

        // composed = [8,6,4,2,0]; window [0,3) => [8,6,4]
        const rowsReq = sent.find((r) => r.kind === "rowsByRowid") as { rowids: number[]; viewKey: string };
        expect(rowsReq.rowids).toEqual([8, 6, 4]);

        ctl.addResponse({ kind: "rows", sourceName: "s", viewKey: rowsReq.viewKey, rowids: [8, 6, 4], rows: rowsFor([8, 6, 4]) });
        expect(success).toHaveBeenCalledTimes(1);
        expect(aOf(success.mock.calls[0][0])).toEqual([8, 6, 4]);
        expect(success.mock.calls[0][1]).toBe(5); // composed length
    });
});


describe("RowCacheController — errors", () => {
    test("an error fails the parked callbacks", () => {
        const { ctl } = harness({ datasetLength: 100, headSize: 0, tailSize: 0 });
        const fail = jest.fn();
        ctl.getRows({ sourceName: "s", start: 0, end: 5 }, jest.fn(), fail);
        ctl.addError();
        expect(fail).toHaveBeenCalledTimes(1);
    });
});
