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
import { StateOrchestrator, StatsModel, forceStats, requestStats, touchesDataflow } from "./StateOrchestrator";
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

// A session whose stats the server did not plan to compute says so in
// df_meta.stats (rows-first c5): the tier it is headed for, whether to ask for
// it on its own (`auto_request`, absent means true) and the columns whose
// styling needs stats now (`demand_columns`). With auto_request false the
// scheduler asks for those columns and nothing else.
const policy = (over: Record<string, any> = {}) => ({
    status: "not_computed",
    tier: "schema",
    gen: 3,
    reason: "size",
    tier_target: "schema",
    estimate: { rows: 12_400_000, cols: 44 },
    auto_request: false,
    requestable: ["scalar", "full"],
    ...over,
});

describe("auto_request false: only the demand columns are asked for (rows-first c5)", () => {
    // The request for demand columns: scoped to them, at the tier that carries
    // min and max, and not forced (it is the scheduler's, not the user's).
    const demand = (gen: number, columns: string[], tier = "scalar") => request(gen, { columns, tier });
    const sendFirst = async (model: FakeModel) => {
        const orchestrator = start(model);
        rowsArrived(model);
        await tick();
        return orchestrator;
    };

    it.each(["pending", "not_computed"])("asks for nothing when the status is %s and no column needs stats", async (status) => {
        const model = makeModel(policy({ status }));
        await sendFirst(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it.each(["pending", "not_computed"])("asks for nothing when demand_columns is empty (status %s)", async (status) => {
        const model = makeModel(policy({ status, demand_columns: [] }));
        await sendFirst(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it.each(["pending", "not_computed"])("sends one scoped request for the demand columns (status %s)", async (status) => {
        const model = makeModel(policy({ status, demand_columns: ["a", "c"] }));
        model.state.visible_columns = ["a", "b"];
        await sendFirst(model);
        // The visible columns are not what it asks for, and nothing is forced.
        expect(model.sent).toEqual([demand(3, ["a", "c"])]);
        expect(model.sent[0]).not.toHaveProperty("force");
    });

    it("goes out after the first rows, not before, and once however many row responses follow", async () => {
        const model = makeModel(policy({ demand_columns: ["a"] }));
        start(model);
        await tick(100);
        expect(model.sent).toEqual([]);
        rowsArrived(model);
        rowsArrived(model);
        await tick();
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([demand(3, ["a"])]);
    });

    it("asks for the next step of the demand for each reply that is not final, and stops at the final one", async () => {
        const model = makeModel(policy({ demand_columns: ["a", "c"] }));
        await sendFirst(model);
        expect(model.sent).toHaveLength(1);

        // A partial reply is a new df_data_dict under the same df_meta.
        model.set("df_data_dict", dict([statRow("min")]));
        await tick();
        expect(model.sent).toEqual([demand(3, ["a", "c"]), demand(3, ["a", "c"])]);

        // The final reply says the session is still not computed (it ran for some
        // columns only), in a new df_meta.
        model.set("df_data_dict", dict([statRow("min"), statRow("max")]));
        model.set("df_meta", meta(policy({ demand_columns: ["a", "c"] })));
        await tick(10_000);
        expect(model.sent).toHaveLength(2);
    });

    it("does not ask again for the same demand after a refusal or a reply that carried no stats", async () => {
        const model = makeModel(policy({ demand_columns: ["a"] }));
        await sendFirst(model);
        // stats_aborted not_requestable and a ceiling reply both replace df_meta only.
        model.set("df_meta", meta(policy({ demand_columns: ["a"], reason: "ceiling" })));
        await tick(10_000);
        expect(model.sent).toEqual([demand(3, ["a"])]);

        // A full frame for the same state (a search highlight) does not restart it.
        model.frame({ df_meta: meta(policy({ demand_columns: ["a"], reason: "ceiling" })), df_data_dict: dict() });
        await tick();
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([demand(3, ["a"])]);
    });

    it("a full frame for the same state does not end it: the reply to the request in flight is still answered", async () => {
        const model = makeModel(policy({ demand_columns: ["a", "c"] }));
        await sendFirst(model);
        // A search highlight comes back as a full frame with the same stats.
        model.frame({ df_meta: meta(policy({ demand_columns: ["a", "c"] })), df_data_dict: dict([statRow("dtype")]) });
        await tick(10_000);
        expect(model.sent).toEqual([demand(3, ["a", "c"])]);

        model.set("df_data_dict", dict([statRow("dtype"), statRow("min")]));
        await tick();
        expect(model.sent).toEqual([demand(3, ["a", "c"]), demand(3, ["a", "c"])]);
    });

    it("asks for the next gen's demand after a state change", async () => {
        const model = makeModel(policy({ demand_columns: ["a"] }));
        await sendFirst(model);
        model.set("df_meta", meta(policy({ demand_columns: ["a"] })));
        await tick();

        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        model.frame({ df_meta: meta(policy({ gen: 4, demand_columns: ["b"] })), df_data_dict: dict() });
        await tick();
        rowsArrived(model);
        await tick(DEBOUNCE);
        expect(model.sent).toEqual([demand(3, ["a"]), demand(4, ["b"])]);
    });

    it("asks for a changed list of demand columns on the same gen", async () => {
        const model = makeModel(policy({ demand_columns: ["a"] }));
        await sendFirst(model);
        model.set("df_meta", meta(policy({ demand_columns: ["a"] })));
        await tick();

        model.set("df_meta", meta(policy({ demand_columns: ["a", "d"] })));
        await tick();
        rowsArrived(model);
        await tick(DEBOUNCE);
        expect(model.sent).toEqual([demand(3, ["a"]), demand(3, ["a", "d"])]);
    });

    it("asks at the tier the policy allows: full when scalar is not requestable", async () => {
        const model = makeModel(policy({ demand_columns: ["a"], requestable: ["full"] }));
        await sendFirst(model);
        expect(model.sent).toEqual([demand(3, ["a"], "full")]);
    });

    it("asks for nothing when the policy allows no tier above schema (a ceiling)", async () => {
        const model = makeModel(policy({ demand_columns: ["a"], requestable: [], reason: "ceiling" }));
        await sendFirst(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it("a pending session with auto_request false is not run whole", async () => {
        const model = makeModel(policy({ status: "pending", demand_columns: ["a"] }));
        await sendFirst(model);
        expect(model.sent).toEqual([demand(3, ["a"])]);
    });

    it("leaves a session that does auto-request alone: demand_columns do not change its whole run", async () => {
        for (const over of [{ auto_request: true }, { auto_request: undefined }]) {
            const model = makeModel({ status: "pending", tier: "schema", gen: 3, demand_columns: ["a"], ...over });
            model.state.visible_columns = ["b"];
            await sendFirst(model);
            expect(model.sent).toEqual([request(3, { columns: ["b"] })]);
        }
    });

    it("does not ask when the policy says not computed and auto_request is true (nothing is served yet)", async () => {
        const model = makeModel(policy({ auto_request: true, demand_columns: ["a"] }));
        await sendFirst(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });
});

describe("forceStats: the control's request (rows-first c5)", () => {
    const notComputed = (over: Record<string, any> = {}) => policy({ gen: 5, ...over });

    it("asks for the smallest tier the policy allows: scalar before full", () => {
        const model = makeModel(notComputed());
        expect(forceStats(model)).toBe(true);
        expect(model.sent).toEqual([request(5, { force: true, tier: "scalar" })]);
    });

    it("asks for full when the server leaves requestable out (its default)", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 5, reason: "host" });
        expect(forceStats(model)).toBe(true);
        expect(model.sent).toEqual([request(5, { force: true, tier: "full" })]);
    });

    it("asks for the tier above the one reached once scalar is in", () => {
        const model = makeModel(notComputed({ tier: "scalar" }));
        expect(forceStats(model)).toBe(true);
        expect(model.sent).toEqual([request(5, { force: true, tier: "full" })]);
    });

    it("asks for scalar alone when only scalar is requestable", () => {
        const model = makeModel(notComputed({ requestable: ["scalar"] }));
        expect(forceStats(model)).toBe(true);
        expect(model.sent).toEqual([request(5, { force: true, tier: "scalar" })]);
    });

    it("sends nothing when no tier is left to ask for", () => {
        const model = makeModel(notComputed({ requestable: [], reason: "ceiling" }));
        const before = model.get("df_meta");
        expect(forceStats(model)).toBe(false);
        expect(model.sent).toEqual([]);
        expect(model.get("df_meta")).toBe(before);
    });

    // The server cannot push a frame to a capable client, so the control marks
    // the stats pending itself: the loading text and the placeholder rows show
    // at once, and the control is gone, so a second click cannot start a second
    // chain of requests.
    it("marks the stats pending in a new df_meta, keeping the rest of it, so the control gives way to the loading state", () => {
        const model = makeModel(notComputed());
        const before = model.get("df_meta");
        expect(forceStats(model)).toBe(true);
        const after = model.get("df_meta");
        expect(after).not.toBe(before);
        expect(after.stats).toEqual({ ...notComputed(), status: "pending" });
        expect(after.total_rows).toBe(before.total_rows);
    });

    it("sends nothing when df_meta carries no stats.gen", () => {
        const model = makeModel();
        expect(forceStats(model)).toBe(false);
        expect(model.sent).toEqual([]);
    });

    it("names no columns for the whole table, whatever the grid shows", () => {
        const model = makeModel(notComputed());
        model.state.visible_columns = ["a", "b"];
        forceStats(model);
        expect(model.sent[0]).not.toHaveProperty("columns");
    });

    it("has a per-column form: the columns it is given, with the same force and tier", () => {
        const model = makeModel(notComputed());
        model.state.visible_columns = ["a", "b"];
        expect(forceStats(model, { columns: ["c"] })).toBe(true);
        expect(model.sent).toEqual([request(5, { force: true, tier: "scalar", columns: ["c"] })]);
    });
});

describe("a forced run is continued by the scheduler (rows-first c5)", () => {
    const notComputed = (over: Record<string, any> = {}) => policy({ gen: 5, ...over });
    const forced = (extra: Record<string, any> = {}) => request(5, { force: true, tier: "scalar", ...extra });
    const startForced = async (opts?: { columns?: string[] }, stats = notComputed()) => {
        const model = makeModel(stats);
        start(model);
        forceStats(model, opts);
        await tick();
        return model;
    };

    it("asks again, with the same force, tier and columns, for each reply that is not final", async () => {
        const model = await startForced({ columns: ["c"] });
        expect(model.sent).toEqual([forced({ columns: ["c"] })]);

        // No reply yet: nothing more goes out, however long the server takes.
        await tick(10_000);
        expect(model.sent).toHaveLength(1);

        model.set("df_data_dict", dict([statRow("min")]));
        await tick();
        expect(model.sent).toEqual([forced({ columns: ["c"] }), forced({ columns: ["c"] })]);
        model.set("df_data_dict", dict([statRow("min"), statRow("max")]));
        await tick();
        expect(model.sent).toHaveLength(3);
    });

    it("sends the whole-table form again as the whole-table form", async () => {
        const model = await startForced();
        model.state.visible_columns = ["a"];
        model.set("df_data_dict", dict([statRow("min")]));
        await tick();
        expect(model.sent).toEqual([forced(), forced()]);
    });

    it("stops at a final reply, which replaces df_meta", async () => {
        const model = await startForced();
        model.set("df_data_dict", dict([statRow("min")]));
        await tick();
        expect(model.sent).toHaveLength(2);

        model.set("df_data_dict", dict([statRow("min"), statRow("max")]));
        model.set("df_meta", meta({ status: "complete", tier: "scalar", gen: 5 }));
        await tick(10_000);
        expect(model.sent).toHaveLength(2);
    });

    it("stops at a ceiling reply or a refusal, which change df_meta and nothing else", async () => {
        const model = await startForced();
        model.set("df_meta", meta(notComputed({ reason: "ceiling" })));
        await tick(10_000);
        expect(model.sent).toEqual([forced()]);
    });

    it("drops the run when the gen moves on, and does not continue a late reply", async () => {
        const model = await startForced();
        // The next gen's frame, with the stats pending as the run left them: only
        // the gen differs.
        model.frame({ df_meta: meta(notComputed({ gen: 6, status: "pending" })), df_data_dict: dict() });
        await tick();
        // A reply for the old run arrives after the new frame.
        model.set("df_data_dict", dict([statRow("min")]));
        await tick(10_000);
        expect(model.sent).toEqual([forced()]);
    });

    it("is not started for a run recorded against a gen that is not on screen", async () => {
        const model = makeModel(notComputed());
        start(model);
        model.set("stats_forced", { gen: 9, tier: "scalar" });
        await tick();
        model.set("df_data_dict", dict([statRow("min")]));
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it("does not continue a run recorded before the scheduler started", async () => {
        const model = makeModel(notComputed());
        model.state.stats_forced = { gen: 5, tier: "scalar" };
        start(model);
        model.set("df_data_dict", dict([statRow("min")]));
        await tick(10_000);
        expect(model.sent).toEqual([]);
    });

    it("a full frame for the same gen ends the run: the model shows what the server says, and a late reply is not continued", async () => {
        const model = await startForced();
        // The server's own view of the session is still not computed.
        model.frame({ df_meta: meta(notComputed()), df_data_dict: dict([statRow("dtype")]) });
        await tick(10_000);
        model.set("df_data_dict", dict([statRow("dtype"), statRow("min")]));
        await tick(10_000);
        expect(model.sent).toEqual([forced()]);
    });

    it("does nothing for a model nobody started a scheduler on", async () => {
        const model = makeModel(notComputed());
        forceStats(model);
        model.set("df_data_dict", dict([statRow("min")]));
        await tick(10_000);
        expect(model.sent).toEqual([forced()]);
    });
});

// A session the server sized to scalar (or a host named scalar for) is not
// computed until the client asks, and auto_request (absent means true) says the
// client should ask up to tier_target on its own (rows-first c5b). The first
// frame: not_computed, a reason of size or host, tier_target scalar, and no
// requestable, since that lists the tiers above the target.
const scalarTarget = (over: Record<string, any> = {}) => ({
    status: "not_computed",
    tier: "schema",
    gen: 3,
    reason: "size",
    tier_target: "scalar",
    estimate: { rows: 10_800_000, cols: 43 },
    ...over,
});

describe("a scalar target is requested on its own (rows-first c5b)", () => {
    // The request: the target tier, incremental, not forced, and naming no
    // columns (a tier with columns scopes the run to them).
    const target = (gen = 3) => request(gen, { tier: "scalar" });
    const startTarget = async (stats: Record<string, any> = scalarTarget()) => {
        const model = makeModel(stats);
        model.state.visible_columns = ["a", "b"];
        start(model);
        rowsArrived(model);
        await tick();
        return model;
    };

    it.each(["size", "host"])("sends one incremental request for the target tier, without a click (reason %s)", async (reason) => {
        const model = await startTarget(scalarTarget({ reason }));
        expect(model.sent).toEqual([target()]);
        await tick(10_000);
        expect(model.sent).toHaveLength(1);
    });

    it("does not force the tier, and adds neither the grid's columns nor any other", async () => {
        const model = await startTarget();
        expect(model.sent[0]).not.toHaveProperty("force");
        expect(model.sent[0]).not.toHaveProperty("columns");
    });

    it("asks after the first rows, or when the wait for them times out, and once however many row responses follow", async () => {
        const model = makeModel(scalarTarget());
        start(model);
        await tick(100);
        expect(model.sent).toEqual([]);
        rowsArrived(model);
        rowsArrived(model);
        await tick();
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([target()]);

        const quiet = makeModel(scalarTarget());
        start(quiet);
        await tick(FIRST_PAINT_TIMEOUT);
        expect(quiet.sent).toEqual([target()]);
    });

    // The server sends no frame to a capable client while it runs, so the
    // scheduler marks the stats pending as the control does: the loading text
    // shows at once, and the control is not there to start a second run.
    it("marks the stats pending in a new df_meta, keeping the rest of it", async () => {
        const model = makeModel(scalarTarget());
        const before = model.get("df_meta");
        start(model);
        rowsArrived(model);
        await tick();
        const after = model.get("df_meta");
        expect(after).not.toBe(before);
        expect(after.stats).toEqual({ ...scalarTarget(), status: "pending" });
        expect(after.total_rows).toBe(before.total_rows);
    });

    it("asks again, with the same request, for each reply that is not final, and stops at the final one", async () => {
        const model = await startTarget();
        expect(model.sent).toEqual([target()]);

        model.set("df_data_dict", dict([statRow("min")]));
        await tick();
        expect(model.sent).toEqual([target(), target()]);
        model.set("df_data_dict", dict([statRow("min"), statRow("max")]));
        await tick();
        expect(model.sent).toHaveLength(3);

        // The final reply leaves the session not computed, with the tier reached.
        model.set("df_data_dict", dict([statRow("min"), statRow("max"), statRow("std")]));
        model.set("df_meta", meta(scalarTarget({ reached_tier: "scalar", computed_columns: ["a"] })));
        await tick(10_000);
        expect(model.sent).toHaveLength(3);
    });

    it("does not ask again after a refusal, though the session is not computed again for the same target", async () => {
        const model = await startTarget();
        // stats_aborted not_requestable (a server that does not serve the tier) replaces df_meta only.
        model.set("df_meta", meta(scalarTarget()));
        await tick(10_000);
        expect(model.sent).toEqual([target()]);

        // Nor for a full frame under the same gen.
        model.frame({ df_meta: meta(scalarTarget()), df_data_dict: dict([statRow("dtype")]) });
        await tick();
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([target()]);
    });

    it("asks for the next gen's target after a state change, and not again for the gen it left", async () => {
        const model = await startTarget();
        model.set("buckaroo_state", bState({ post_processing: "log_scale" }));
        model.frame({ df_meta: meta(scalarTarget({ gen: 4 })), df_data_dict: dict() });
        await tick();
        rowsArrived(model);
        await tick(DEBOUNCE);
        expect(model.sent).toEqual([target(3), target(4)]);
        await tick(10_000);
        expect(model.sent).toHaveLength(2);
    });

});

describe("the control and the scheduler read the tier reached (rows-first c5b)", () => {
    const schemaTarget = (over: Record<string, any> = {}) => policy({ gen: 5, ...over });

    it("forceStats asks for full once scalar has been reached", () => {
        const model = makeModel(schemaTarget({ reached_tier: "scalar" }));
        expect(forceStats(model)).toBe(true);
        expect(model.sent).toEqual([request(5, { force: true, tier: "full" })]);
    });

    it.each([
        ["full has been reached", { reached_tier: "full" }],
        ["scalar is all the server allows and has been reached", { requestable: ["scalar"], reached_tier: "scalar" }],
    ])("forceStats sends nothing when %s", (_name, over) => {
        const model = makeModel(schemaTarget(over));
        const before = model.get("df_meta");
        expect(forceStats(model)).toBe(false);
        expect(model.sent).toEqual([]);
        expect(model.get("df_meta")).toBe(before);
    });

    it("the scheduler does not ask for the demand columns' scalar stats once scalar has been reached for the whole table", async () => {
        const model = makeModel(policy({ demand_columns: ["a"], reached_tier: "scalar" }));
        start(model);
        rowsArrived(model);
        await tick(10_000);
        expect(model.sent).toEqual([]);
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

    // Plan 3 s3.4: the control sends {stats_gen, scope, tier, force}, with a
    // `columns` form per column. On a forced request `columns` names the
    // columns the request is for, so the grid's visible columns (an ordering
    // hint on the scheduler's requests) are not added to it (rows-first c5).
    it("adds no columns hint to a forced request, however many columns the grid shows", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 7 });
        model.state.visible_columns = ["a", "b"];
        expect(requestStats(model, { force: true })).toBe(true);
        expect(model.sent).toEqual([request(7, { force: true })]);
        expect(model.sent[0]).not.toHaveProperty("columns");
    });

    it("carries the tier it is asked for", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 7 });
        expect(requestStats(model, { force: true, tier: "scalar" })).toBe(true);
        expect(model.sent).toEqual([request(7, { force: true, tier: "scalar" })]);
    });

    it("names the columns it is given, in place of the visible-columns hint", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 7 });
        model.state.visible_columns = ["a", "b"];
        expect(requestStats(model, { force: true, tier: "scalar", columns: ["c"] })).toBe(true);
        expect(requestStats(model, { columns: ["d"] })).toBe(true);
        expect(model.sent).toEqual([request(7, { force: true, tier: "scalar", columns: ["c"] }), request(7, { columns: ["d"] })]);
    });

    // The server reads `columns` with a `tier` as the scope of the run, so the
    // grid's columns (an ordering hint) must not ride on a request for a tier
    // (rows-first c5b).
    it("adds no columns hint to a request for a tier, forced or not", () => {
        const model = makeModel({ status: "not_computed", tier: "schema", gen: 7 });
        model.state.visible_columns = ["a", "b"];
        expect(requestStats(model, { tier: "scalar" })).toBe(true);
        expect(model.sent).toEqual([request(7, { tier: "scalar" })]);
        expect(model.sent[0]).not.toHaveProperty("columns");
    });

    it("sends no tier and no columns the caller did not name, and no hint for an empty list", () => {
        const model = makeModel(pending(7));
        expect(requestStats(model, { columns: [] })).toBe(true);
        expect(model.sent).toEqual([request(7)]);
        expect(model.sent[0]).not.toHaveProperty("tier");
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

    // Rows-first c5: a not computed session, the control, and the replies.
    describe("a session whose stats are not computed", () => {
        const forcedRequest = (extra: Record<string, any> = {}) => request(3, { force: true, tier: "scalar", ...extra });

        it("sends nothing on its own, and the control's forced run goes tier by tier to its final reply", async () => {
            const { ws, model } = makeSocketModel(policy({ gen: 3 }));
            rowsFromServer(ws);
            await tick(10_000);
            expect(ws.sent).toEqual([]);

            expect(forceStats(model)).toBe(true);
            expect(ws.sent).toEqual([forcedRequest()]);

            // The control marked the stats pending, and they stay pending until the
            // final reply says otherwise.
            expect(model.get("df_meta").stats.status).toBe("pending");
            const pendingMeta = model.get("df_meta");
            ws.deliver({ ...update(3, "min", false, 2), tier: "scalar" });
            await tick();
            expect(ws.sent).toEqual([forcedRequest(), forcedRequest()]);
            expect(model.get("df_meta")).toBe(pendingMeta);

            ws.deliver({ ...update(3, "max", true, 0), tier: "scalar" });
            await tick(10_000);
            expect(ws.sent).toHaveLength(2);
            expect(model.get("df_meta").stats).toEqual({ status: "complete", tier: "scalar", gen: 3 });
            expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "min", "max"]);
        });

        it("a request over the ceiling ends in the ceiling message, and nothing more is sent", async () => {
            const { ws, model } = makeSocketModel(policy({ gen: 3 }));
            forceStats(model);
            ws.deliver({ type: "stats_update", stats_gen: 3, scope: "raw", tier: "full", final: true, status: "not_computed", reason: "ceiling" });
            await tick(10_000);
            expect(ws.sent).toEqual([forcedRequest()]);
            expect(model.get("df_meta").stats).toMatchObject({ status: "not_computed", reason: "ceiling", gen: 3 });
        });

        it("a request the server refuses with not_requestable returns the session to not computed and ends the run", async () => {
            const { ws, model } = makeSocketModel(policy({ gen: 3 }));
            forceStats(model);
            expect(model.get("df_meta").stats.status).toBe("pending");
            ws.deliver({ type: "stats_aborted", stats_gen: 3, current_gen: 3, scope: "raw", reason: "not_requestable" });
            await tick(10_000);
            expect(ws.sent).toEqual([forcedRequest()]);
            expect(model.get("df_meta").stats).toEqual(policy({ gen: 3 }));
        });

        it("a run for some columns ends not computed, and the control can ask again", async () => {
            const { ws, model } = makeSocketModel(policy({ gen: 3 }));
            forceStats(model, { columns: ["a"] });
            expect(ws.sent).toEqual([forcedRequest({ columns: ["a"] })]);

            ws.deliver({ ...update(3, "min", true, 0), tier: "scalar", status: "not_computed" });
            await tick(10_000);
            expect(ws.sent).toHaveLength(1);
            // The session is not computed again, and says which column the run filled.
            expect(model.get("df_meta").stats).toEqual({ ...policy({ gen: 3 }), computed_columns: ["a"] });

            expect(forceStats(model)).toBe(true);
            expect(ws.sent).toEqual([forcedRequest({ columns: ["a"] }), forcedRequest()]);
            expect(ws.sent[1]).not.toHaveProperty("columns");
        });

        it("asks for the demand columns after the first rows and nothing else", async () => {
            const { ws, model } = makeSocketModel(policy({ gen: 3, demand_columns: ["a"] }));
            model.set("visible_columns", ["a", "b"]);
            await tick(100);
            expect(ws.sent).toEqual([]);

            rowsFromServer(ws);
            await tick();
            expect(ws.sent).toEqual([request(3, { columns: ["a"], tier: "scalar" })]);

            // The reply carries stats for those columns and leaves the session not computed.
            ws.deliver({ ...update(3, "min", true, 0), tier: "scalar", status: "not_computed" });
            await tick(10_000);
            expect(ws.sent).toHaveLength(1);
            expect(model.get("df_meta").stats.status).toBe("not_computed");
            expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "min"]);
        });

        it("a demand run's final reply names the columns it filled", async () => {
            const { ws, model } = makeSocketModel(policy({ gen: 3, demand_columns: ["a"] }));
            rowsFromServer(ws);
            await tick();
            ws.deliver({ ...update(3, "min", true, 0), tier: "scalar", status: "not_computed" });
            await tick(10_000);
            expect(model.get("df_meta").stats).toEqual({
                ...policy({ gen: 3, demand_columns: ["a"] }),
                computed_columns: ["a"],
            });
        });
    });

    // The two defects the integration run found on the merged stack
    // (rows-first c5b): a scalar target was never requested, and the control
    // asked for scalar on every click.
    describe("tier bookkeeping (rows-first c5b)", () => {
        const scalarRun = (stat: string, final: boolean, remaining: number, gen = 3) => ({
            ...update(gen, stat, final, remaining),
            tier: "scalar",
            // The server's final reply to a scalar run: the session is still not computed.
            ...(final ? { status: "not_computed", reason: "size" } : {}),
        });
        const schemaTarget = (gen = 3) => policy({ gen, tier_target: "schema", requestable: ["scalar", "full"] });
        const scalarRequest = request(3, { tier: "scalar" });
        const forcedRequest = (extra: Record<string, any> = {}) => request(3, { force: true, tier: "scalar", ...extra });

        it("a scalar target is requested without a click, walked to its final reply, and not requested again", async () => {
            const { ws, model } = makeSocketModel(scalarTarget());
            model.set("visible_columns", ["a"]);
            await tick(100);
            expect(ws.sent).toEqual([]);

            rowsFromServer(ws);
            await tick();
            expect(ws.sent).toEqual([scalarRequest]);
            expect(model.get("df_meta").stats.status).toBe("pending");

            ws.deliver(scalarRun("min", false, 1));
            await tick();
            expect(ws.sent).toEqual([scalarRequest, scalarRequest]);
            expect(model.get("df_meta").stats.status).toBe("pending");

            ws.deliver(scalarRun("max", true, 0));
            await tick(10_000);
            expect(ws.sent).toHaveLength(2);
            expect(model.get("df_meta").stats).toEqual({
                ...scalarTarget(),
                computed_columns: ["a"],
                reached_tier: "scalar",
            });
            expect(model.get("df_data_dict").all_stats.map((r: any) => r.index)).toEqual(["dtype", "min", "max"]);
        });

        it("a gen change stops the run, drops its late replies, and the new gen's target is requested", async () => {
            const { ws, model } = makeSocketModel(scalarTarget());
            rowsFromServer(ws);
            await tick();
            ws.deliver(scalarRun("min", false, 1));
            await tick();
            expect(ws.sent).toHaveLength(2);

            ws.deliver({ type: "initial_state", df_meta: meta(scalarTarget({ gen: 4 })), df_data_dict: dict() });
            await tick();
            ws.deliver(scalarRun("max", true, 0));
            await tick(100);
            expect(ws.sent).toHaveLength(2);
            expect(model.get("df_meta").stats).toEqual(scalarTarget({ gen: 4 }));

            rowsFromServer(ws);
            await tick(DEBOUNCE);
            expect(ws.sent[2]).toEqual(request(4, { tier: "scalar" }));
            ws.deliver(scalarRun("max", true, 0, 4));
            await tick(10_000);
            expect(ws.sent).toHaveLength(3);
            expect(model.get("df_meta").stats.reached_tier).toBe("scalar");
        });

        it("a server that refuses the tier ends the run and is not asked again", async () => {
            const { ws, model } = makeSocketModel(scalarTarget());
            rowsFromServer(ws);
            await tick();
            ws.deliver({ type: "stats_aborted", stats_gen: 3, current_gen: 3, scope: "raw", reason: "not_requestable" });
            await tick(10_000);
            expect(ws.sent).toEqual([scalarRequest]);
            expect(model.get("df_meta").stats).toEqual(scalarTarget());
        });

        it("a ceiling reply to the automatic request ends in the ceiling message and nothing more is sent", async () => {
            const { ws, model } = makeSocketModel(scalarTarget());
            rowsFromServer(ws);
            await tick();
            ws.deliver({ type: "stats_update", stats_gen: 3, scope: "raw", tier: "scalar", final: true, status: "not_computed", reason: "ceiling" });
            await tick(10_000);
            expect(ws.sent).toEqual([scalarRequest]);
            expect(model.get("df_meta").stats).toEqual(scalarTarget({ reason: "ceiling" }));
        });

        it("the control asks for scalar, then full: each final reply moves it up, and after full there is nothing to ask for", async () => {
            const { ws, model } = makeSocketModel(schemaTarget());
            expect(forceStats(model)).toBe(true);
            expect(ws.sent).toEqual([forcedRequest()]);

            // The reply the integration run saw: final, tier scalar, still not computed.
            ws.deliver(scalarRun("min", true, 0));
            await tick(10_000);
            expect(model.get("df_meta").stats).toMatchObject({ status: "not_computed", tier: "schema", reached_tier: "scalar" });

            expect(forceStats(model)).toBe(true);
            expect(ws.sent).toEqual([forcedRequest(), forcedRequest({ tier: "full" })]);

            ws.deliver({ ...update(3, "mean", true, 0), tier: "full" });
            await tick(10_000);
            expect(model.get("df_meta").stats).toEqual({ status: "complete", tier: "full", gen: 3 });
            expect(forceStats(model)).toBe(false);
            expect(ws.sent).toHaveLength(2);
        });

        it("a server that allows scalar only: after the scalar run the control has nothing left to ask for", async () => {
            const { ws, model } = makeSocketModel({ ...schemaTarget(), requestable: ["scalar"] });
            forceStats(model);
            ws.deliver(scalarRun("min", true, 0));
            await tick(10_000);
            expect(forceStats(model)).toBe(false);
            expect(ws.sent).toEqual([forcedRequest()]);
        });

        it("a gen change resets the tier reached: the control asks for scalar again on the new gen", async () => {
            const { ws, model } = makeSocketModel(schemaTarget());
            forceStats(model);
            ws.deliver(scalarRun("min", true, 0));
            await tick(10_000);
            expect(model.get("df_meta").stats.reached_tier).toBe("scalar");

            ws.deliver({ type: "initial_state", df_meta: meta(schemaTarget(4)), df_data_dict: dict() });
            await tick();
            expect(model.get("df_meta").stats).not.toHaveProperty("reached_tier");
            expect(forceStats(model)).toBe(true);
            expect(ws.sent[1]).toEqual(request(4, { force: true, tier: "scalar" }));
        });

    });
});
