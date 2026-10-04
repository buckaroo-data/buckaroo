/**
 * StateOrchestrator — the client scheduler for the stats wire (rows-first c4).
 *
 * A session the server defers stats for sends a stats-free first frame with
 * df_meta.stats.status "pending". The scheduler asks for the stats once the
 * first rows have arrived (`stats_request`), asks again for each reply that
 * leaves the stats pending, and stands down when the state changes. The merge
 * of the replies is StatsChannel's; the scheduler only watches the model.
 *
 * The scheduler tests drive a fake model the way WebSocketModel drives a real
 * one (set a key, emit its change event). The last block builds a real
 * WebSocketModel from a fake socket.
 */
import { StateOrchestrator, StatsModel, requestStats, touchesDataflow } from "./StateOrchestrator";
import { WebSocketModel } from "./WebSocketModel";

class FakeModel implements StatsModel {
    sent: any[] = [];
    private handlers = new Map<string, Set<Function>>();

    constructor(public state: Record<string, any>) {}

    get(key: string) {
        return this.state[key];
    }
    set(key: string, value: any) {
        this.state[key] = value;
        this.emit(`change:${key}`, value);
    }
    send(msg: any) {
        this.sent.push(msg);
    }
    on(event: string, handler: (...args: any[]) => void) {
        if (!this.handlers.has(event)) this.handlers.set(event, new Set());
        this.handlers.get(event)!.add(handler);
    }
    off(event: string, handler: (...args: any[]) => void) {
        this.handlers.get(event)?.delete(handler);
    }
    emit(event: string, ...args: any[]) {
        for (const h of Array.from(this.handlers.get(event) ?? [])) h(...args);
    }
    listenerCount() {
        return Array.from(this.handlers.values()).reduce((n, set) => n + set.size, 0);
    }
    /** A full frame: each key lands and fires its change event in turn, as
     *  WebSocketModel's initial_state branch does. */
    frame(msg: Record<string, any>) {
        for (const [key, value] of Object.entries(msg)) this.set(key, value);
    }
}

const meta = (stats?: Record<string, any>) => ({
    total_rows: 3, columns: 2, filtered_rows: 3, rows_shown: 3,
    ...(stats === undefined ? {} : { stats }),
});
const pending = (gen: number) => ({ status: "pending", tier: "schema", gen });
const complete = (gen: number) => ({ status: "complete", tier: "full", gen });
const dict = (rows: any[] = []) => ({ all_stats: rows });
const statRow = (stat: string) => ({ index: stat, level_0: stat, a: 1 });
// Typed loosely: the server's buckaroo_state also carries keys (search_string)
// that BuckarooState does not declare.
const bState = (over: Record<string, any> = {}): any => ({
    sampled: false, cleaning_method: false, quick_command_args: {}, post_processing: false,
    df_display: "main", show_commands: false, ...over,
});

// Every request is a time-boxed step (rows-first c4b); the earlier phases sent
// the whole run, so this helper had no `incremental`.
const request = (gen: number, extra: Record<string, any> = {}) => ({
    type: "stats_request", stats_gen: gen, scope: "raw", incremental: true, ...extra,
});

const makeModel = (stats?: Record<string, any>) =>
    new FakeModel({ df_meta: meta(stats), df_data_dict: dict(), buckaroo_state: bState() });

/** The first rows reached the client: WebSocketModel emits msg:custom once it
 *  has paired an infinite_resp with its parquet frame. */
const rowsArrived = (model: FakeModel) =>
    model.emit("msg:custom", { type: "infinite_resp", key: { start: 0, end: 3 }, length: 3 }, []);

const start = (model: FakeModel, opts: Record<string, number> = {}) => {
    const orchestrator = new StateOrchestrator({ model, ...opts });
    orchestrator.start();
    return orchestrator;
};

// With the defaults, a state change waits 2 x 250 ms before it asks again.
const DEBOUNCE = 500;
const FIRST_PAINT_TIMEOUT = 1500;

// Runs due timers and every promise continuation they leave behind.
const tick = (ms = 0) => jest.advanceTimersByTimeAsync(ms);

beforeEach(() => {
    jest.useFakeTimers();
});

afterEach(() => {
    jest.useRealTimers();
});

describe("when nothing is pending", () => {
    it("requests nothing for a session whose df_meta has no stats (every session today)", async () => {
        const model = makeModel();
        start(model);
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it.each(["complete", "not_computed", "error"])("requests nothing when the status is %s", async (status) => {
        const model = makeModel({ status, tier: "schema", gen: 3 });
        start(model);
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });
});

describe("the first request", () => {
    it("goes out after the first infinite_resp, not before", async () => {
        const model = makeModel(pending(3));
        start(model);
        await tick(100);
        expect(model.sent).toEqual([]);

        rowsArrived(model);
        await tick();
        expect(model.sent).toEqual([request(3)]);
    });

    it("goes out anyway when no rows come (an empty frame, the summary view)", async () => {
        const model = makeModel(pending(3));
        start(model);
        await tick(FIRST_PAINT_TIMEOUT - 1);
        expect(model.sent).toEqual([]);

        await tick(2);
        expect(model.sent).toEqual([request(3)]);
    });

    it("carries no force flag", async () => {
        const model = makeModel(pending(3));
        start(model);
        rowsArrived(model);
        await tick();
        expect(model.sent[0]).not.toHaveProperty("force");
    });

    it("is sent once, however many row responses follow", async () => {
        const model = makeModel(pending(3));
        start(model);
        rowsArrived(model);
        rowsArrived(model);
        await tick();
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([request(3)]);
    });
});

describe("one request per reply", () => {
    const afterFirstRequest = async () => {
        const model = makeModel(pending(3));
        const orchestrator = start(model);
        rowsArrived(model);
        await tick();
        return { model, orchestrator };
    };

    it("asks again for each reply that leaves the stats pending, and stops at the final one", async () => {
        const { model } = await afterFirstRequest();
        expect(model.sent).toEqual([request(3)]);

        // No reply yet: nothing more goes out, however long the server takes.
        await tick(10_000);
        expect(model.sent).toEqual([request(3)]);

        // A partial reply is a new df_data_dict under the same df_meta, which is
        // what StatsChannel does for a stats_update that is not final.
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick();
        expect(model.sent).toEqual([request(3), request(3)]);
        await tick(10_000);
        expect(model.sent).toHaveLength(2);

        model.set("df_data_dict", dict([statRow("mean"), statRow("std")]));
        await tick();
        expect(model.sent).toHaveLength(3);

        // The final reply also sets df_meta.stats to complete.
        model.set("df_data_dict", dict([statRow("mean"), statRow("std"), statRow("max")]));
        model.set("df_meta", meta(complete(3)));
        await tick(10_000);
        expect(model.sent).toHaveLength(3);
    });

    it("reads a reply the same way whichever of the two events comes first", async () => {
        const { model } = await afterFirstRequest();
        model.set("df_meta", meta(complete(3)));
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick(10_000);
        expect(model.sent).toEqual([request(3)]);
    });

    it.each([
        ["df_meta then df_data_dict", ["df_meta", "df_data_dict"]],
        ["df_data_dict then df_meta", ["df_data_dict", "df_meta"]],
    ])("does not take a full frame for the same state as a reply (%s)", async (_label, order) => {
        // A search term that changes only the highlight comes back as a full
        // initial_state for the same stats_gen, with a new df_meta and a new dict.
        const { model } = await afterFirstRequest();
        const full: Record<string, any> = { df_meta: meta(pending(3)), df_data_dict: dict([statRow("dtype")]) };
        model.frame(Object.fromEntries(order.map((k) => [k, full[k]])));
        await tick(10_000);
        expect(model.sent).toEqual([request(3)]);
    });

    it("stops when the server reports an error", async () => {
        const { model } = await afterFirstRequest();
        model.set("df_meta", meta({ status: "error", tier: "schema", gen: 3, reason: "stats_failed" }));
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick(10_000);
        expect(model.sent).toEqual([request(3)]);
    });

    it("stops when the server says the stats are not computed", async () => {
        const { model } = await afterFirstRequest();
        model.set("df_meta", meta({ status: "not_computed", tier: "schema", gen: 3 }));
        await tick(10_000);
        expect(model.sent).toEqual([request(3)]);
    });
});

describe("incremental requests (rows-first c4b)", () => {
    const sendFirst = async (model: FakeModel) => {
        start(model);
        rowsArrived(model);
        await tick();
    };

    it("asks for a time-boxed step, with no columns hint while the grid has not reported its columns", async () => {
        const model = makeModel(pending(3));
        await sendFirst(model);
        expect(model.sent).toEqual([{ type: "stats_request", stats_gen: 3, scope: "raw", incremental: true }]);
        expect(model.sent[0]).not.toHaveProperty("columns");
        expect(model.sent[0]).not.toHaveProperty("force");
    });

    it("sends the columns the grid shows as the hint", async () => {
        const model = makeModel(pending(3));
        model.state.visible_columns = ["b", "c"];
        await sendFirst(model);
        expect(model.sent).toEqual([request(3, { columns: ["b", "c"] })]);
    });

    it("sends no hint for an empty list of visible columns", async () => {
        const model = makeModel(pending(3));
        model.state.visible_columns = [];
        await sendFirst(model);
        expect(model.sent).toEqual([request(3)]);
    });

    it("reads the hint again for each request of a run, so a column scrolled into view goes out next", async () => {
        const model = makeModel(pending(3));
        model.state.visible_columns = ["a", "b"];
        await sendFirst(model);

        model.set("visible_columns", ["e", "f"]);
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick();
        model.set("df_data_dict", dict([statRow("mean"), statRow("std")]));
        await tick();
        expect(model.sent).toEqual([
            request(3, { columns: ["a", "b"] }),
            request(3, { columns: ["e", "f"] }),
            request(3, { columns: ["e", "f"] }),
        ]);
    });

    it("sends the same shape for the first request of the next gen after a state change", async () => {
        const model = makeModel(pending(3));
        model.state.visible_columns = ["a", "b"];
        await sendFirst(model);

        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        model.frame({ df_meta: meta(pending(4)), df_data_dict: dict() });
        await tick();
        rowsArrived(model);
        await tick(DEBOUNCE);
        expect(model.sent).toEqual([request(3, { columns: ["a", "b"] }), request(4, { columns: ["a", "b"] })]);
    });
});

describe("a state change", () => {
    const pendingAt = async (gen: number) => {
        const model = makeModel(pending(gen));
        const orchestrator = start(model);
        rowsArrived(model);
        await tick();
        return { model, orchestrator };
    };

    // The server answers a dataflow change with a frame for the next stats_gen,
    // then the grid's refetch brings rows. They are separate messages, so the
    // scheduler has read the frame by the time the rows arrive.
    const nextFrame = async (model: FakeModel, gen: number) => {
        model.frame({ df_meta: meta(pending(gen)), df_data_dict: dict() });
        await tick();
        rowsArrived(model);
    };

    it("stops the requests for the old state, then asks once for the new one", async () => {
        const { model } = await pendingAt(3);
        expect(model.sent).toEqual([request(3)]);

        // The user changes a dataflow field while the request is out.
        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        await tick(10);
        // The reply to the old request lands. It is not followed by another.
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick(10);
        await nextFrame(model, 4);

        await tick(DEBOUNCE - 1);
        expect(model.sent).toEqual([request(3)]);
        await tick(1);
        expect(model.sent).toEqual([request(3), request(4)]);
        await tick(10_000);
        expect(model.sent).toHaveLength(2);
    });

    it("reads a frame whose dict comes before its df_meta as the next state, not as a reply", async () => {
        const { model } = await pendingAt(3);
        // The frame for the next gen carries its dict before its df_meta.
        model.frame({ df_data_dict: dict(), df_meta: meta(pending(4)) });
        await tick();
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([request(3), request(4)]);
    });

    it.each([
        ["post_processing", { post_processing: "log_scale" }],
        ["cleaning_method", { cleaning_method: "aggressive" }],
        ["quick_command_args", { quick_command_args: { search: ["x"] } }],
    ])("a %s change cancels a request that is waiting out its delay", async (_field, change) => {
        const { model } = await pendingAt(3);
        await nextFrame(model, 4);
        await tick(300);

        model.set("buckaroo_state", bState(change));
        await tick(300);
        // 600 ms in: the request that was due at 500 ms never went out.
        expect(model.sent).toEqual([request(3)]);

        await nextFrame(model, 5);
        await tick(DEBOUNCE - 1);
        expect(model.sent).toEqual([request(3)]);
        await tick(1);
        expect(model.sent).toEqual([request(3), request(5)]);
    });

    it.each([
        ["search_string (the #1015 path)", { search_string: "x" }],
        ["df_display", { df_display: "summary" }],
        ["show_commands", { show_commands: "1" }],
        ["sampled", { sampled: "sample" }],
    ])("a %s-only change is skipped", async (_label, change) => {
        const { model } = await pendingAt(3);
        await nextFrame(model, 4);
        await tick(300);

        model.set("buckaroo_state", bState(change));
        await tick(200);
        // The request is still due at 500 ms, as if nothing had changed.
        expect(model.sent).toEqual([request(3), request(4)]);
    });

    it("a search_string-only change does not interrupt a chain of replies", async () => {
        const { model } = await pendingAt(3);
        model.set("buckaroo_state", bState({ search_string: "x" }));
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick();
        expect(model.sent).toEqual([request(3), request(3)]);
    });

    it("a frame that repeats the same dataflow state is not a state change", async () => {
        // Every full frame carries buckaroo_state back as the client sent it.
        const { model } = await pendingAt(3);
        model.set("buckaroo_state", bState());
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick();
        expect(model.sent).toEqual([request(3), request(3)]);
    });

    it("waits out the delay for a state change made after the earlier stats completed", async () => {
        const { model } = await pendingAt(3);
        await tick(250); // a request that took as long as the default assumes, so the delay is DEBOUNCE
        model.set("df_data_dict", dict([statRow("mean")]));
        model.set("df_meta", meta(complete(3))); // the final reply
        await tick();

        // The first state asked at once; this one is a change to it.
        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        await nextFrame(model, 4);
        await tick(DEBOUNCE - 1);
        expect(model.sent).toEqual([request(3)]);
        await tick(1);
        expect(model.sent).toEqual([request(3), request(4)]);
    });

    it("waits out the delay for the first state change of a model that started with its stats complete", async () => {
        const model = makeModel(complete(3));
        start(model);
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);

        model.set("buckaroo_state", bState({ quick_command_args: { search: ["a"] } }));
        await nextFrame(model, 4);
        await tick(DEBOUNCE - 1);
        expect(model.sent).toEqual([]);
        await tick(1);
        expect(model.sent).toEqual([request(4)]);
    });

    it("asks again for the same state when the server never answers the change with a frame", async () => {
        const { model } = await pendingAt(3);
        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        await tick(FIRST_PAINT_TIMEOUT + DEBOUNCE);
        expect(model.sent).toEqual([request(3), request(3)]);
    });

    it("waits 2 x the last request's time, within the limits, before the next state's request", async () => {
        const model = makeModel(pending(3));
        const orchestrator = start(model, { minDebounceMs: 100, maxDebounceMs: 2000 });
        expect(orchestrator.computeDebounce()).toBe(500);

        rowsArrived(model);
        await tick(400);
        model.set("df_data_dict", dict([statRow("mean")])); // the reply, 400 ms after the request
        await tick();
        expect(orchestrator.computeDebounce()).toBe(800);

        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        await nextFrame(model, 4);
        await tick(799);
        expect(model.sent).toHaveLength(2);
        await tick(1);
        expect(model.sent).toHaveLength(3);
        expect(model.sent[2]).toEqual(request(4));
    });

    it("measures a request once: later events do not stretch the delay", async () => {
        const model = makeModel(pending(3));
        const orchestrator = start(model, { minDebounceMs: 100, maxDebounceMs: 20_000 });
        rowsArrived(model);
        await tick(400);
        model.set("df_data_dict", dict([statRow("mean")]));
        model.set("df_meta", meta(complete(3))); // the final reply
        await tick();
        expect(orchestrator.computeDebounce()).toBe(800);

        // A full frame for the finished state, long afterwards.
        await tick(10_000);
        model.frame({ df_meta: meta(complete(3)), df_data_dict: dict() });
        await tick();
        expect(orchestrator.computeDebounce()).toBe(800);
    });

    it.each([
        [10, 100],
        [400, 800],
        [5000, 2000],
    ])("computeDebounce after a %i ms request is %i ms (floor 100, ceiling 2000)", async (elapsed, expected) => {
        const model = makeModel(pending(3));
        const orchestrator = start(model, { minDebounceMs: 100, maxDebounceMs: 2000 });
        rowsArrived(model);
        await tick(elapsed);
        model.set("df_data_dict", dict([statRow("mean")]));
        await tick();
        expect(orchestrator.computeDebounce()).toBe(expected);
    });
});

describe("requestStats", () => {
    it("sends a stats_request for the gen the model shows", () => {
        const model = makeModel(pending(7));
        expect(requestStats(model)).toBe(true);
        expect(model.sent).toEqual([request(7)]);
    });

    it("force sends force: true, which the Compute summary stats control uses", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 7 });
        expect(requestStats(model, { force: true })).toBe(true);
        expect(model.sent).toEqual([request(7, { force: true })]);
    });

    it("carries the columns the grid shows, for a forced request too", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 7 });
        model.state.visible_columns = ["a", "b"];
        expect(requestStats(model, { force: true })).toBe(true);
        expect(model.sent).toEqual([request(7, { force: true, columns: ["a", "b"] })]);
    });

    it("sends nothing when df_meta carries no stats.gen", () => {
        const model = makeModel();
        expect(requestStats(model)).toBe(false);
        expect(requestStats(model, { force: true })).toBe(false);
        expect(model.sent).toEqual([]);
    });
});

describe("touchesDataflow", () => {
    it("is true for each field the server reruns the dataflow for", () => {
        expect(touchesDataflow(bState(), bState({ post_processing: "x" }))).toBe(true);
        expect(touchesDataflow(bState(), bState({ cleaning_method: "x" }))).toBe(true);
        expect(touchesDataflow(bState(), bState({ quick_command_args: { search: ["x"] } }))).toBe(true);
    });

    it("is false for the others, and for an equal quick_command_args that is a new object", () => {
        expect(touchesDataflow(bState(), bState({ search_string: "x" }))).toBe(false);
        expect(touchesDataflow(bState(), bState({ df_display: "summary" }))).toBe(false);
        expect(touchesDataflow(bState({ quick_command_args: { search: ["x"] } }), bState({ quick_command_args: { search: ["x"] } }))).toBe(false);
    });

    it("is false when there is no earlier state to compare with", () => {
        expect(touchesDataflow(undefined, bState({ post_processing: "x" }))).toBe(false);
    });
});

describe("start and stop", () => {
    it("stop removes every listener and cancels the pending request", async () => {
        const model = makeModel(pending(3));
        const orchestrator = start(model);
        expect(model.listenerCount()).toBeGreaterThan(0);

        rowsArrived(model);
        orchestrator.stop();
        expect(model.listenerCount()).toBe(0);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it("start is idempotent: a second call adds no listeners", () => {
        const model = makeModel(pending(3));
        const orchestrator = start(model);
        const listeners = model.listenerCount();
        orchestrator.start();
        expect(model.listenerCount()).toBe(listeners);
    });

    it("can start again after a stop", async () => {
        const model = makeModel(pending(3));
        const orchestrator = start(model);
        orchestrator.stop();
        orchestrator.start();
        rowsArrived(model);
        await tick();
        expect(model.sent).toEqual([request(3)]);
    });
});

// The scheduler is started by WebSocketModel, so a session reached through
// BuckarooServerView or the standalone page gets it with no wiring of its own.
describe("wired into WebSocketModel", () => {
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
        deliverBinary() {
            this.onmessage?.({ data: new ArrayBuffer(8) } as MessageEvent);
        }
    }

    const update = (gen: number, stat: string, final: boolean, remaining?: number) => ({
        type: "stats_update",
        stats_gen: gen,
        scope: "raw",
        tier: "full",
        final,
        ...(remaining === undefined ? {} : { remaining }),
        payload: { format: "json", layout: "wide", data: [{ index: stat, level_0: stat, a: 1 }] },
        elapsed_ms: 5,
    });

    const makeSocketModel = (stats?: Record<string, any>) => {
        const ws = new FakeSocket();
        const model = new WebSocketModel(ws as unknown as WebSocket, {
            df_meta: meta(stats),
            df_data_dict: { all_stats: [{ index: "dtype", level_0: "dtype", a: "int64" }] },
            buckaroo_state: bState(),
        });
        return { ws, model };
    };
    const rowsFromServer = (ws: FakeSocket) => {
        ws.deliver({ type: "infinite_resp", key: { start: 0, end: 3 }, length: 3 });
        ws.deliverBinary();
    };

    it("requests the stats after the first rows, once per reply, and stops at the final one", async () => {
        const { ws, model } = makeSocketModel(pending(3));
        await tick(100);
        expect(ws.sent).toEqual([]);

        rowsFromServer(ws);
        await tick();
        expect(ws.sent).toEqual([request(3)]);

        ws.deliver(update(3, "mean", false));
        await tick();
        expect(ws.sent).toEqual([request(3), request(3)]);

        ws.deliver(update(3, "std", true));
        await tick(10_000);
        expect(ws.sent).toHaveLength(2);
        expect(model.get("df_meta").stats.status).toBe("complete");
        expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "mean", "std"]);
    });

    it("walks partial replies to the final one: one request per reply, the stats pending until the last", async () => {
        const { ws, model } = makeSocketModel(pending(3));
        model.set("visible_columns", ["a"]);
        const pendingMeta = model.get("df_meta");
        rowsFromServer(ws);
        await tick();
        const asked = request(3, { columns: ["a"] });
        expect(ws.sent).toEqual([asked]);

        for (const [i, stat] of ["mean", "std", "max"].entries()) {
            ws.deliver(update(3, stat, false, 3 - i));
            await tick();
            expect(ws.sent).toEqual(Array(i + 2).fill(asked));
            // The merge adds the rows, and the stats stay pending: the same
            // df_meta, so the placeholders and the loading text stay.
            expect(model.get("df_meta")).toBe(pendingMeta);
            expect(model.get("df_meta").stats.status).toBe("pending");
        }
        expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "mean", "std", "max"]);

        // The final reply carries the complete all_stats.
        ws.deliver({
            ...update(3, "min", true, 0),
            payload: {
                format: "json",
                layout: "wide",
                data: ["dtype", "mean", "std", "max", "min"].map((stat) => ({ index: stat, level_0: stat, a: stat === "dtype" ? "int64" : 2 })),
            },
        });
        await tick(10_000);
        expect(ws.sent).toHaveLength(4);
        expect(model.get("df_meta").stats).toEqual({ status: "complete", tier: "full", gen: 3 });
        expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "mean", "std", "max", "min"]);
        expect(model.get("df_data_dict").all_stats[1].a).toBe(2);
    });

    it("ends the run at a whole-run final from a server that ignores the incremental field", async () => {
        const { ws, model } = makeSocketModel(pending(3));
        rowsFromServer(ws);
        await tick();
        expect(ws.sent).toEqual([request(3)]);

        // An older server runs every unit and answers final, with no `remaining`.
        ws.deliver(update(3, "mean", true));
        await tick(10_000);
        expect(ws.sent).toHaveLength(1);
        expect(model.get("df_meta").stats.status).toBe("complete");
        expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "mean"]);
    });

    it("stops a run when the gen changes, drops its late replies, and starts one for the new gen", async () => {
        const { ws, model } = makeSocketModel(pending(3));
        model.set("visible_columns", ["a"]);
        rowsFromServer(ws);
        await tick();
        ws.deliver(update(3, "mean", false, 2));
        await tick();
        expect(ws.sent).toEqual([request(3, { columns: ["a"] }), request(3, { columns: ["a"] })]);

        // A state change moved the server to gen 4 with the run for gen 3 in flight.
        ws.deliver({ type: "initial_state", df_meta: meta(pending(4)), df_data_dict: dict() });
        await tick();
        ws.deliver(update(3, "std", false, 1));
        await tick(100);
        expect(ws.sent).toHaveLength(2);
        expect(model.get("df_data_dict").all_stats).toEqual([]);

        rowsFromServer(ws);
        await tick(DEBOUNCE);
        expect(ws.sent[2]).toEqual(request(4, { columns: ["a"] }));

        // The new run chains like the old one did.
        ws.deliver(update(4, "mean", false, 1));
        await tick();
        expect(ws.sent).toHaveLength(4);
        expect(ws.sent[3]).toEqual(request(4, { columns: ["a"] }));
        ws.deliver(update(4, "std", true, 0));
        await tick(10_000);
        expect(ws.sent).toHaveLength(4);
        expect(model.get("df_meta").stats.status).toBe("complete");
    });

    it("moves on to the next gen when a state change frame arrives", async () => {
        const { ws } = makeSocketModel(pending(3));
        rowsFromServer(ws);
        await tick();
        expect(ws.sent).toEqual([request(3)]);

        ws.deliver({ type: "initial_state", df_meta: meta(pending(4)), df_data_dict: dict() });
        await tick();
        rowsFromServer(ws);
        await tick(DEBOUNCE);
        expect(ws.sent).toEqual([request(3), request(4)]);
    });

    it("sends nothing for a model whose df_meta has no stats", async () => {
        const { ws } = makeSocketModel();
        rowsFromServer(ws);
        await tick(10_000);
        expect(ws.sent).toEqual([]);
    });
});
