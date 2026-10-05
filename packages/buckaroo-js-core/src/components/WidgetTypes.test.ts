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
    autoRequestTier,
    canRequestStats,
    demandTier,
    nextRequestTier,
    statsAutoRequest,
    statsOverCeiling,
    statsRequestable,
    tierReached,
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

// The server's ceiling keeps the stats from being computed. It says so with
// reason "ceiling" when the ceiling cut a request down; when the server sized the
// session at the ceiling itself, the reason is "size" and nothing is left to ask
// for.
describe("statsOverCeiling", () => {
    it("is true for reason ceiling, whatever requestable lists", () => {
        expect(statsOverCeiling(stats({ reason: "ceiling" }))).toBe(true);
        expect(statsOverCeiling(stats({ reason: "ceiling", requestable: ["scalar", "full"] }))).toBe(true);
    });

    it("is true for a session the server sized with nothing left above it to ask for", () => {
        expect(statsOverCeiling(stats({ reason: "size", requestable: [] }))).toBe(true);
        expect(statsOverCeiling(stats({ reason: "size", tier: "scalar", requestable: ["scalar"] }))).toBe(true);
    });

    it("is false while a tier is left to ask for", () => {
        expect(statsOverCeiling(stats({ reason: "size", requestable: ["scalar", "full"] }))).toBe(false);
        expect(statsOverCeiling(stats({ reason: "size", tier: "scalar", requestable: ["scalar", "full"] }))).toBe(false);
    });

    it("is false when the server named no requestable (its default is full)", () => {
        expect(statsOverCeiling(stats({ reason: "size" }))).toBe(false);
    });

    it("is false for the reasons that are not about size", () => {
        expect(statsOverCeiling(stats({ reason: "host", requestable: [] }))).toBe(false);
        expect(statsOverCeiling(stats({ reason: "cost", requestable: [] }))).toBe(false);
    });

    it.each(["pending", "complete", "error"] as const)("is false when the status is %s", (status) => {
        expect(statsOverCeiling(stats({ status, reason: "ceiling" }))).toBe(false);
    });

    it("is false without stats", () => {
        expect(statsOverCeiling(undefined)).toBe(false);
    });
});

// The server keeps `tier` at the tier a not computed session was published at,
// so a run for the whole table that reached scalar leaves it "schema". The
// client keeps what the final replies said in `reached_tier` (rows-first c5b),
// and the helpers read the higher of the two.
describe("the tier a session has reached (rows-first c5b)", () => {
    it("follows the server's tier and the client's reached_tier, whichever is higher", () => {
        expect(tierReached(stats({ tier: "scalar" }))).toBe("scalar");
        expect(tierReached(stats({ reached_tier: "scalar" }))).toBe("scalar");
        expect(tierReached(stats({ tier: "schema", reached_tier: "full" }))).toBe("full");
        expect(tierReached(stats({ tier: "full", reached_tier: "scalar" }))).toBe("full");
    });

    it("moves nextRequestTier up: scalar, then full, then nothing", () => {
        const policy = { requestable: ["scalar", "full"] };
        expect(nextRequestTier(stats(policy))).toBe("scalar");
        expect(nextRequestTier(stats({ ...policy, reached_tier: "scalar" }))).toBe("full");
        expect(nextRequestTier(stats({ ...policy, reached_tier: "full" }))).toBeUndefined();
    });

    it("leaves no tier to ask for when the server allows scalar only and it has been reached", () => {
        expect(nextRequestTier(stats({ requestable: ["scalar"], reached_tier: "scalar" }))).toBeUndefined();
        expect(canRequestStats(stats({ requestable: ["scalar"], reached_tier: "scalar" }))).toBe(false);
    });

    it("canRequestStats is false once the highest requestable tier has been reached", () => {
        expect(canRequestStats(stats({ requestable: ["scalar", "full"], reached_tier: "full" }))).toBe(false);
    });
});

// The server says auto_request when the client should ask for stats up to
// tier_target on its own (absent means true). A session sized to scalar is not
// computed until the client asks, so the scheduler asks for that tier, unless the
// ceiling or the cost guard is why nothing is computed.
describe("autoRequestTier (rows-first c5b)", () => {
    const scalarTarget = (over: Partial<DFMetaStats> = {}) =>
        stats({ reason: "size", tier_target: "scalar", estimate: { rows: 10_800_000, cols: 43 }, ...over });

    it("is the target tier for a session the server sized to scalar, with auto_request absent", () => {
        expect(autoRequestTier(scalarTarget())).toBe("scalar");
        expect(autoRequestTier(scalarTarget({ auto_request: true }))).toBe("scalar");
    });

    it("is the target tier for a scalar a host named", () => {
        expect(autoRequestTier(scalarTarget({ reason: "host" }))).toBe("scalar");
    });

    it("does not depend on requestable, which lists the tiers above the target", () => {
        expect(autoRequestTier(scalarTarget({ requestable: [] }))).toBe("scalar");
        expect(autoRequestTier(scalarTarget({ requestable: ["full"] }))).toBe("scalar");
    });

});
