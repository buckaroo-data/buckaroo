/**
 * StatsChannel — the client half of the stats wire (rows-first c2).
 *
 * A capable client receives a stats-free `initial_state` (df_meta.stats.status
 * "pending"), asks for the stats and merges the `stats_update` that answers,
 * keyed by `stats_gen`. These tests drive a WebSocketModel with a fake socket,
 * the way the server's frames reach it.
 */
import { WebSocketModel } from "./WebSocketModel";
import { withStatsCapability } from "./StatsChannel";
import { decodeDFData } from "../components/DFViewerParts/resolveDFData";

// A wide summary-stats envelope (parquet_b64, layout "wide") as the server
// sends one; the decoder tests use the same fixture.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const wideFixture = require("../components/DFViewerParts/test-fixtures/summary_stats_parquet_b64.json");

// The real decoder, except that an envelope carrying `hold` waits on `gate`,
// so a test can deliver a frame while a decode is in flight.
let gate: Promise<void> = Promise.resolve();
jest.mock("../components/DFViewerParts/resolveDFData", () => {
    const actual = jest.requireActual("../components/DFViewerParts/resolveDFData");
    return {
        ...actual,
        decodeDFData: jest.fn(async (env: any, buffers?: DataView[]) => {
            if (env && env.hold) await gate;
            return actual.decodeDFData(env, buffers);
        }),
    };
});

class FakeSocket {
    readyState = 1; // WebSocket.OPEN
    onmessage: ((e: MessageEvent) => void) | null = null;
    sent: any[] = [];
    send(data: string) {
        this.sent.push(JSON.parse(data));
    }
    deliver(msg: object) {
        this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
    }
}

// Lets every promise continuation (the payload decode) run.
const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

const row = (stat: string, cells: Record<string, any>) => ({ index: stat, level_0: stat, ...cells });

// What the schema tier ships: identity rows only.
const schemaStats = () => [
    row("dtype", { a: "int64", b: "float64", c: "object" }),
    row("length", { a: 3, b: 3, c: 3 }),
];

const metaFor = (stats?: Record<string, any>) => ({
    total_rows: 3, columns: 3, filtered_rows: 3, rows_shown: 3,
    ...(stats === undefined ? {} : { stats }),
});

const pending = (gen: number) => ({ status: "pending", tier: "schema", gen });

const frame = (gen: number | undefined, allStats: any = schemaStats()) => ({
    type: "initial_state",
    df_meta: metaFor(gen === undefined ? undefined : pending(gen)),
    df_data_dict: { all_stats: allStats },
});

// The server's payload is a wide DFEnvelope; the json format decodes to the
// same row shape without a parquet fixture.
const update = (gen: number, rows: any[], extra: object = {}) => ({
    type: "stats_update",
    stats_gen: gen,
    scope: "raw",
    tier: "full",
    final: true,
    payload: { format: "json", layout: "wide", data: rows },
    elapsed_ms: 12.5,
    ...extra,
});

function makeModel(gen: number | undefined = 3, allStats: any = schemaStats()) {
    const ws = new FakeSocket();
    const model = new WebSocketModel(ws as unknown as WebSocket, {
        df_meta: metaFor(gen === undefined ? undefined : pending(gen)),
        df_data_dict: { all_stats: allStats },
    });
    const events: { event: string; value: any }[] = [];
    for (const key of ["df_data_dict", "df_meta"]) {
        model.on(`change:${key}`, (value: any) => events.push({ event: `change:${key}`, value }));
    }
    return { ws, model, events };
}

describe("withStatsCapability", () => {
    it("adds ?caps=stats_update to a bare URL", () => {
        expect(withStatsCapability("ws://localhost:8700/ws/sales")).toBe("ws://localhost:8700/ws/sales?caps=stats_update");
    });

    it("appends to an existing query string", () => {
        expect(withStatsCapability("ws://h/ws/s?token=abc")).toBe("ws://h/ws/s?token=abc&caps=stats_update");
    });

    it("extends an existing caps value", () => {
        expect(withStatsCapability("ws://h/ws/s?caps=other")).toBe("ws://h/ws/s?caps=other,stats_update");
    });

    it("keeps the fragment last", () => {
        expect(withStatsCapability("ws://h/ws/s#frag")).toBe("ws://h/ws/s?caps=stats_update#frag");
    });
});

describe("stats_update merge", () => {
    it("key-merges the payload's columns into all_stats and keeps the other columns", async () => {
        const { ws, model } = makeModel(3);
        ws.deliver(update(3, [
            row("length", { a: 3, b: 5 }),
            row("mean", { a: 2, b: 4.5 }),
        ]));
        await settle();
        expect(model.get("df_data_dict").all_stats).toEqual([
            row("dtype", { a: "int64", b: "float64", c: "object" }),
            row("length", { a: 3, b: 5, c: 3 }),
            row("mean", { a: 2, b: 4.5 }),
        ]);
    });

    it("does not let a null in the payload erase a value already merged", async () => {
        const { ws, model } = makeModel(3);
        // The wide pivot pads a stat a column did not carry with null.
        ws.deliver(update(3, [row("dtype", { a: null, b: "float32" })]));
        await settle();
        const dtype = model.get("df_data_dict").all_stats.find((r: any) => r.index === "dtype");
        expect(dtype).toEqual(row("dtype", { a: "int64", b: "float32", c: "object" }));
    });

    it("assigns a new df_data_dict and leaves the previous objects untouched", async () => {
        const { ws, model, events } = makeModel(3);
        const before = model.get("df_data_dict");
        const beforeStats = before.all_stats;
        const snapshot = JSON.parse(JSON.stringify(beforeStats));
        ws.deliver(update(3, [row("length", { a: 99 }), row("mean", { a: 2 })]));
        await settle();
        const after = model.get("df_data_dict");
        expect(after).not.toBe(before);
        expect(after.all_stats).not.toBe(beforeStats);
        expect(beforeStats).toEqual(snapshot);
        const dictEvents = events.filter((e) => e.event === "change:df_data_dict");
        expect(dictEvents).toHaveLength(1);
        expect(dictEvents[0].value).toBe(after);
    });

    it("merges onto an all_stats that arrived as an undecoded envelope", async () => {
        const { ws, model } = makeModel(3);
        // A later initial_state hands the model the dict as the server sent it.
        ws.deliver(frame(4, { format: "json", layout: "wide", data: schemaStats() }));
        ws.deliver(update(4, [row("mean", { a: 2, b: 4.5, c: null })]));
        await settle();
        const stats = model.get("df_data_dict").all_stats;
        expect(Array.isArray(stats)).toBe(true);
        expect(stats.map((r: any) => r.index)).toEqual(["dtype", "length", "mean"]);
    });

    it("keeps the other df_data_dict keys", async () => {
        const ws = new FakeSocket();
        const model = new WebSocketModel(ws as unknown as WebSocket, {
            df_meta: metaFor(pending(3)),
            df_data_dict: { all_stats: schemaStats(), empty: [], main: [{ a: 1 }] },
        });
        ws.deliver(update(3, [row("mean", { a: 2 })]));
        await settle();
        const dict = model.get("df_data_dict");
        expect(dict.empty).toEqual([]);
        expect(dict.main).toEqual([{ a: 1 }]);
        expect(dict.all_stats).toHaveLength(3);
    });

    it("merges a wide parquet_b64 payload as the server sends it", async () => {
        const { ws, model } = makeModel(3, [row("orig_col_name", { a: "first" })]);
        const decoded: any[] = await decodeDFData(wideFixture);
        expect(decoded.length).toBeGreaterThan(1);
        ws.deliver(update(3, [], { payload: wideFixture }));
        await settle();
        const stats = model.get("df_data_dict").all_stats;
        expect(stats[0]).toEqual(row("orig_col_name", { a: "first" }));
        for (const decodedRow of decoded) {
            expect(stats).toContainEqual(decodedRow);
        }
    });

    it("builds all_stats when the model holds no dict yet", async () => {
        const ws = new FakeSocket();
        const model = new WebSocketModel(ws as unknown as WebSocket, { df_meta: metaFor(pending(3)) });
        ws.deliver(update(3, [row("mean", { a: 2 })]));
        await settle();
        expect(model.get("df_data_dict")).toEqual({ all_stats: [row("mean", { a: 2 })] });
    });

    it("adds all_stats to a dict that has none", async () => {
        const ws = new FakeSocket();
        const model = new WebSocketModel(ws as unknown as WebSocket, {
            df_meta: metaFor(pending(3)),
            df_data_dict: { main: [{ a: 1 }] },
        });
        ws.deliver(update(3, [row("mean", { a: 2 })]));
        await settle();
        expect(model.get("df_data_dict")).toEqual({ main: [{ a: 1 }], all_stats: [row("mean", { a: 2 })] });
    });

    it("applies updates that arrive back to back, in order", async () => {
        const { ws, model } = makeModel(3);
        ws.deliver(update(3, [row("mean", { a: 2 })], { final: false }));
        ws.deliver(update(3, [row("mean", { b: 4.5 }), row("max", { a: 9 })]));
        await settle();
        const stats = model.get("df_data_dict").all_stats;
        expect(stats.find((r: any) => r.index === "mean")).toEqual(row("mean", { a: 2, b: 4.5 }));
        expect(stats.find((r: any) => r.index === "max")).toEqual(row("max", { a: 9 }));
    });
});

describe("stats_update and df_meta.stats", () => {
    it("a final update marks the stats complete at the update's tier", async () => {
        const { ws, model, events } = makeModel(3);
        const metaBefore = model.get("df_meta");
        ws.deliver(update(3, [row("mean", { a: 2 })]));
        await settle();
        const meta = model.get("df_meta");
        expect(meta).not.toBe(metaBefore);
        expect(meta.stats).toEqual({ status: "complete", tier: "full", gen: 3 });
        expect(meta.total_rows).toBe(3);
        expect(events.filter((e) => e.event === "change:df_meta")).toHaveLength(1);
    });

    it("a non-final update merges but leaves the status pending", async () => {
        const { ws, model, events } = makeModel(3);
        ws.deliver(update(3, [row("mean", { a: 2 })], { final: false }));
        await settle();
        expect(model.get("df_data_dict").all_stats).toHaveLength(3);
        expect(model.get("df_meta").stats.status).toBe("pending");
        expect(events.filter((e) => e.event === "change:df_meta")).toHaveLength(0);
    });
});

describe("stats_gen", () => {
    it("drops a stats_update whose stats_gen is not the expected one", async () => {
        const { ws, model, events } = makeModel(3);
        ws.deliver(update(2, [row("mean", { a: 2 })]));
        ws.deliver(update(3, [row("max", { a: 9 })]));
        await settle();
        expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "length", "max"]);
        expect(events.filter((e) => e.event === "change:df_data_dict")).toHaveLength(1);
    });

    it("advances the expected gen on a broadcast initial_state with no reply_seq", async () => {
        const { ws, model } = makeModel(3);
        ws.deliver(frame(4));
        ws.deliver(update(3, [row("mean", { a: 2 })]));
        await settle();
        expect(model.get("df_data_dict").all_stats).toHaveLength(2);
        ws.deliver(update(4, [row("mean", { a: 2 })]));
        await settle();
        expect(model.get("df_data_dict").all_stats).toHaveLength(3);
    });

    it("discards a merge when an initial_state for a newer gen arrives while it decodes", async () => {
        const { ws, model } = makeModel(3);
        ws.deliver(update(3, [row("mean", { a: 2 })]));
        // Still decoding: the model has not merged anything yet.
        ws.deliver(frame(4, [row("dtype", { a: "int32" })]));
        await settle();
        expect(model.get("df_data_dict").all_stats).toEqual([row("dtype", { a: "int32" })]);
        expect(model.get("df_meta").stats).toEqual(pending(4));
        ws.deliver(update(4, [row("mean", { a: 2 })]));
        await settle();
        expect(model.get("df_data_dict").all_stats).toEqual([row("dtype", { a: "int32" }), row("mean", { a: 2 })]);
    });

    it("merges onto the new dict when a same-gen initial_state replaces it while the old one decodes", async () => {
        let release: () => void = () => {};
        gate = new Promise<void>((resolve) => { release = resolve; });
        try {
            const held = { format: "json", layout: "wide", data: schemaStats(), hold: true };
            const { ws, model } = makeModel(3, held);
            ws.deliver(update(3, [row("mean", { a: 2 })]));
            await settle(); // the update is now waiting on the held decode
            expect((decodeDFData as jest.Mock).mock.calls.some(([env]) => env === held)).toBe(true);
            ws.deliver(frame(3, [row("dtype", { a: "int32" })]));
            release();
            await settle();
            expect(model.get("df_data_dict").all_stats).toEqual([
                row("dtype", { a: "int32" }),
                row("mean", { a: 2 }),
            ]);
            expect(model.get("df_meta").stats).toEqual({ status: "complete", tier: "full", gen: 3 });
        } finally {
            release();
            gate = Promise.resolve();
        }
    });
});

describe("stats_aborted", () => {
    it("marks the stats failed when the run for the expected gen failed", async () => {
        const { ws, model } = makeModel(3);
        ws.deliver({ type: "stats_aborted", stats_gen: 3, current_gen: 3, scope: "raw", reason: "error" });
        await settle();
        expect(model.get("df_meta").stats).toEqual({ status: "error", tier: "schema", gen: 3, reason: "stats_failed" });
    });

    it("marks the stats not computed when the server says they cannot be requested", async () => {
        const { ws, model } = makeModel(3);
        ws.deliver({ type: "stats_aborted", stats_gen: 3, current_gen: 3, scope: "raw", reason: "not_requestable" });
        await settle();
        expect(model.get("df_meta").stats.status).toBe("not_computed");
    });
});
