/**
 * Phase 5 — capacity-bounded LRU registry of views.
 *
 * The widget holds one registry per view *kind* (one for sort views,
 * one for filter views). Each is capped — the design picks 4 so
 * toggling between two columns / filters stays fast at all times.
 */
import { IdentityView, SortView, FilterView } from "./Views";
import { ViewRegistry } from "./ViewRegistry";


const sortV = (key: string) =>
    new SortView(key, "asc", Int32Array.from([0]));
const filterV = (key: string) =>
    new FilterView(key, Int32Array.from([0]));


describe("ViewRegistry — basics", () => {
    test("an empty registry has size 0", () => {
        const r = new ViewRegistry(4);
        expect(r.size()).toBe(0);
        expect(r.has("nope")).toBe(false);
        expect(r.get("nope")).toBeUndefined();
    });

    test("add + get round-trips a view by its viewKey", () => {
        const r = new ViewRegistry(4);
        const v = sortV("age");
        r.add(v);
        expect(r.size()).toBe(1);
        expect(r.has(v.viewKey())).toBe(true);
        expect(r.get(v.viewKey())).toBe(v);
    });

    test("adding two views with different keys keeps both", () => {
        const r = new ViewRegistry(4);
        const v1 = sortV("age");
        const v2 = sortV("name");
        r.add(v1);
        r.add(v2);
        expect(r.size()).toBe(2);
        expect(r.get(v1.viewKey())).toBe(v1);
        expect(r.get(v2.viewKey())).toBe(v2);
    });

    test("adding a view with an existing key replaces in place", () => {
        const r = new ViewRegistry(4);
        const original = sortV("age");
        const replacement = sortV("age");
        r.add(original);
        r.add(replacement);
        expect(r.size()).toBe(1);
        expect(r.get("sort:age:asc")).toBe(replacement);
    });

    test("delete removes a view", () => {
        const r = new ViewRegistry(4);
        const v = sortV("age");
        r.add(v);
        r.delete(v.viewKey());
        expect(r.size()).toBe(0);
        expect(r.has(v.viewKey())).toBe(false);
    });
});


describe("ViewRegistry — LRU eviction", () => {
    test("overflow evicts the least-recently-added view", () => {
        const r = new ViewRegistry(2);
        const v1 = sortV("a");
        const v2 = sortV("b");
        const v3 = sortV("c");
        r.add(v1);
        r.add(v2);
        r.add(v3);
        expect(r.size()).toBe(2);
        expect(r.has(v1.viewKey())).toBe(false); // evicted
        expect(r.has(v2.viewKey())).toBe(true);
        expect(r.has(v3.viewKey())).toBe(true);
    });

    test("get() touches a view so it survives the next eviction", () => {
        const r = new ViewRegistry(2);
        const v1 = sortV("a");
        const v2 = sortV("b");
        r.add(v1);
        r.add(v2);
        // Touch v1 → now v2 is LRU
        expect(r.get(v1.viewKey())).toBe(v1);
        const v3 = sortV("c");
        r.add(v3);
        expect(r.has(v2.viewKey())).toBe(false); // evicted
        expect(r.has(v1.viewKey())).toBe(true);
        expect(r.has(v3.viewKey())).toBe(true);
    });

    test("re-adding an existing key refreshes its LRU position", () => {
        const r = new ViewRegistry(2);
        const v1 = sortV("a");
        const v2 = sortV("b");
        r.add(v1);
        r.add(v2);
        // Re-add v1 with a different instance — v1 is now MRU, v2 LRU
        const v1b = sortV("a");
        r.add(v1b);
        const v3 = sortV("c");
        r.add(v3);
        expect(r.has(v2.viewKey())).toBe(false); // evicted
        expect(r.get(v1b.viewKey())).toBe(v1b);
        expect(r.has(v3.viewKey())).toBe(true);
    });

    test("add returns the evicted view (or undefined if none)", () => {
        const r = new ViewRegistry(2);
        expect(r.add(sortV("a"))).toBeUndefined();
        expect(r.add(sortV("b"))).toBeUndefined();
        const evicted = r.add(sortV("c"));
        expect(evicted).not.toBeUndefined();
        expect(evicted!.viewKey()).toBe("sort:a:asc");
    });

    test("capacity of 0 evicts immediately and never holds anything", () => {
        const r = new ViewRegistry(0);
        expect(r.add(sortV("a"))).not.toBeUndefined(); // immediately evicted
        expect(r.size()).toBe(0);
    });
});


describe("ViewRegistry — view-kind isolation", () => {
    // Sort and filter views with the same metadata key produce different
    // viewKey() strings, so they live in the same registry without
    // colliding — but the design uses two separate registries (one for
    // sorts, one for filters). These tests assert the registry doesn't
    // care which kind you give it.
    test("a single registry can hold sort + filter views with overlapping metadata names", () => {
        const r = new ViewRegistry(4);
        const s = sortV("age");
        const f = filterV("age");
        r.add(s);
        r.add(f);
        expect(r.size()).toBe(2);
        expect(r.get(s.viewKey())).toBe(s);
        expect(r.get(f.viewKey())).toBe(f);
    });

    test("identity view can live in a registry too", () => {
        const r = new ViewRegistry(4);
        const idv = new IdentityView(10);
        r.add(idv);
        expect(r.get("identity")).toBe(idv);
    });
});


describe("ViewRegistry — keys() ordering", () => {
    test("keys() returns viewKeys in LRU-to-MRU order", () => {
        const r = new ViewRegistry(4);
        r.add(sortV("a"));
        r.add(sortV("b"));
        r.add(sortV("c"));
        // MRU is c; LRU is a
        expect(r.keys()).toStrictEqual(["sort:a:asc", "sort:b:asc", "sort:c:asc"]);
    });

    test("get() reorders keys()", () => {
        const r = new ViewRegistry(4);
        r.add(sortV("a"));
        r.add(sortV("b"));
        r.add(sortV("c"));
        r.get("sort:a:asc"); // touch a
        expect(r.keys()).toStrictEqual(["sort:b:asc", "sort:c:asc", "sort:a:asc"]);
    });
});
