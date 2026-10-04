/**
 * df_meta.stats helpers (rows-first c5).
 *
 * The server reports its stats policy to a client that advertises
 * stats_ondemand, and leaves a field out when it holds the documented default:
 * `auto_request` absent means true, `requestable` absent means ["full"]. These
 * helpers read the fields the way the control and the scheduler need them.
 */
import {
    DFMetaStats,
    canRequestStats,
    demandTier,
    nextRequestTier,
    statsAutoRequest,
    statsRequestable,
} from "./WidgetTypes";

const stats = (over: Partial<DFMetaStats> = {}): DFMetaStats => ({
    status: "not_computed",
    tier: "schema",
    gen: 1,
    ...over,
});

describe("defaults for fields the server leaves out", () => {
    it("requestable is ['full'] when absent, and the server's list when present", () => {
        expect(statsRequestable(stats())).toEqual(["full"]);
        expect(statsRequestable(undefined)).toEqual(["full"]);
        expect(statsRequestable(stats({ requestable: ["scalar", "full"] }))).toEqual(["scalar", "full"]);
        expect(statsRequestable(stats({ requestable: [] }))).toEqual([]);
    });

    it("auto_request is true when absent, and false only when the server says so", () => {
        expect(statsAutoRequest(stats())).toBe(true);
        expect(statsAutoRequest(undefined)).toBe(true);
        expect(statsAutoRequest(stats({ auto_request: true }))).toBe(true);
        expect(statsAutoRequest(stats({ auto_request: false }))).toBe(false);
    });
});

describe("nextRequestTier", () => {
    it.each([
        // The smallest tier the policy allows goes first: scalar before full.
        [["scalar", "full"], "schema", "scalar"],
        [["full", "scalar"], "schema", "scalar"],
        [["full"], "schema", "full"],
        [["scalar"], "schema", "scalar"],
        // After scalar has been reached the next one up is offered.
        [["scalar", "full"], "scalar", "full"],
        [["scalar"], "scalar", undefined],
        // Nothing above the target: a ceiling left nothing to ask for.
        [[], "schema", undefined],
    ])("requestable %j with %s reached asks for %s", (requestable, tier, expected) => {
        expect(nextRequestTier(stats({ requestable, tier }))).toBe(expected);
    });

    it("asks for full when the server reports no requestable (its default)", () => {
        expect(nextRequestTier(stats())).toBe("full");
    });

    it("treats a session with no tier as having reached schema", () => {
        expect(nextRequestTier({ status: "not_computed", gen: 1, requestable: ["scalar"] })).toBe("scalar");
    });

    it("ignores names that are not tiers", () => {
        expect(nextRequestTier(stats({ requestable: ["columns", "scalar"] }))).toBe("scalar");
        expect(nextRequestTier(stats({ requestable: ["columns"] }))).toBeUndefined();
    });

    it("is undefined without stats", () => {
        expect(nextRequestTier(undefined)).toBeUndefined();
    });
});

describe("canRequestStats", () => {
    it("is true for a not_computed session with a tier left to ask for", () => {
        expect(canRequestStats(stats())).toBe(true);
        expect(canRequestStats(stats({ requestable: ["scalar", "full"], reason: "size" }))).toBe(true);
        expect(canRequestStats(stats({ reason: "cost" }))).toBe(true);
        expect(canRequestStats(stats({ reason: "host" }))).toBe(true);
    });

    it("is false at the ceiling, whatever requestable lists", () => {
        expect(canRequestStats(stats({ reason: "ceiling" }))).toBe(false);
        expect(canRequestStats(stats({ reason: "ceiling", requestable: ["scalar", "full"] }))).toBe(false);
    });

    it("is false when requestable is empty", () => {
        expect(canRequestStats(stats({ requestable: [] }))).toBe(false);
    });

    it.each(["pending", "complete", "error"] as const)("is false when the status is %s", (status) => {
        expect(canRequestStats(stats({ status }))).toBe(false);
    });

    it("is false without stats", () => {
        expect(canRequestStats(undefined)).toBe(false);
    });
});

describe("demandTier", () => {
    it("is the smallest tier that carries min and max the policy allows", () => {
        expect(demandTier(stats({ requestable: ["scalar", "full"] }))).toBe("scalar");
        expect(demandTier(stats({ requestable: ["scalar"] }))).toBe("scalar");
        expect(demandTier(stats({ requestable: ["full"] }))).toBe("full");
    });

    it("counts the target tier as allowed", () => {
        expect(demandTier(stats({ tier_target: "scalar", requestable: [] }))).toBe("scalar");
    });

    it("is undefined when the policy allows nothing above schema", () => {
        expect(demandTier(stats({ tier_target: "schema", requestable: [] }))).toBeUndefined();
        expect(demandTier(undefined)).toBeUndefined();
    });
});
