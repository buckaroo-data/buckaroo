import { StateOrchestrator, WsLike } from "./StateOrchestrator";

class FakeWs implements WsLike {
    sent: string[] = [];
    send(message: string): void {
        this.sent.push(message);
    }
    last(): Record<string, unknown> {
        return JSON.parse(this.sent[this.sent.length - 1]);
    }
    byType(type: string): Record<string, unknown>[] {
        return this.sent
            .map((s) => JSON.parse(s))
            .filter((m) => m.type === type);
    }
}

describe("StateOrchestrator", () => {
    let ws: FakeWs;
    let orch: StateOrchestrator;

    beforeEach(() => {
        jest.useFakeTimers();
        ws = new FakeWs();
        orch = new StateOrchestrator({ ws, minDebounceMs: 10, maxDebounceMs: 5000 });
    });

    afterEach(() => {
        orch.dispose();
        jest.useRealTimers();
    });

    it("starts with token 0", () => {
        expect(orch.currentToken).toBe(0);
    });

    it("onStateChange bumps token and ships state_change", () => {
        orch.onStateChange({ search_string: "x" });
        expect(orch.currentToken).toBe(1);
        const msg = ws.last();
        expect(msg.type).toBe("state_change");
        expect(msg.state_token).toBe(1);
        expect((msg.new_state as Record<string, unknown>).search_string).toBe("x");
    });

    it("schedules compute_stat_group after the debounce", () => {
        orch.onStateChange({ search_string: "PIZZA" });
        // Only the immediate state_change has been sent so far.
        expect(ws.byType("compute_stat_group")).toHaveLength(0);

        // Default baseline is 500ms × 2× = 1000ms; clamped to maxDebounceMs=5000.
        jest.advanceTimersByTime(999);
        expect(ws.byType("compute_stat_group")).toHaveLength(0);

        jest.advanceTimersByTime(1);
        const reqs = ws.byType("compute_stat_group");
        expect(reqs).toHaveLength(1);
        expect(reqs[0].scope).toBe("filt");
        expect(reqs[0].group).toBe("aggregate");
        expect(reqs[0].state_token).toBe(1);
    });

    it("back-to-back state_changes cancel the previous debounce timer", () => {
        orch.onStateChange({ search_string: "P" });
        jest.advanceTimersByTime(500);
        orch.onStateChange({ search_string: "PI" });
        // The first timer would have fired at t=1000ms; the second
        // resets it so at t=999ms from the SECOND call (= 1499 overall)
        // no compute_stat_group has fired yet.
        jest.advanceTimersByTime(998);
        expect(ws.byType("compute_stat_group")).toHaveLength(0);

        // The second timer fires.
        jest.advanceTimersByTime(2);
        const reqs = ws.byType("compute_stat_group");
        expect(reqs).toHaveLength(1);
        expect(reqs[0].state_token).toBe(2); // second state_change's token
    });

    it("rapid typing produces just one aggregate request, with the latest token", () => {
        // Simulate 5 keystrokes at 100ms intervals — typical typing cadence.
        for (let i = 0; i < 5; i++) {
            orch.onStateChange({ search_string: "P".repeat(i + 1) });
            jest.advanceTimersByTime(100);
        }
        // Default debounce = 1000ms after the last keystroke. No aggregate yet.
        expect(ws.byType("compute_stat_group")).toHaveLength(0);

        jest.advanceTimersByTime(1000);
        const reqs = ws.byType("compute_stat_group");
        // Exactly one aggregate request, with the 5th (final) token.
        expect(reqs).toHaveLength(1);
        expect(reqs[0].state_token).toBe(5);
    });

    it("onStatGroupResult with matching token updates the baseline", () => {
        orch.onStateChange({ search_string: "x" });
        const applied = orch.onStatGroupResult({
            type: "stat_group_result",
            state_token: 1,
            scope: "filt",
            group: "aggregate",
            elapsed_ms: 7500,
        });
        expect(applied).toBe(true);

        // Next debounce is 2× 7500 = 15000ms, clamped to maxDebounceMs=5000.
        expect(orch.computeDebounce("filt")).toBe(5000);
    });

    it("onStatGroupResult with stale token is silently dropped", () => {
        orch.onStateChange({ search_string: "x" });
        orch.onStateChange({ search_string: "xy" });
        // Token is now 2.
        const applied = orch.onStatGroupResult({
            type: "stat_group_result",
            state_token: 1, // stale
            scope: "filt",
            group: "aggregate",
            elapsed_ms: 9999,
        });
        expect(applied).toBe(false);
        // Baseline unchanged — debounce stays at the default.
        expect(orch.computeDebounce("filt")).toBe(1000);
    });

    it("computeDebounce respects minDebounceMs floor", () => {
        const o = new StateOrchestrator({
            ws: new FakeWs(),
            minDebounceMs: 500,
            maxDebounceMs: 3000,
            multiplier: 2,
        });
        o.onStatGroupResult({
            type: "stat_group_result",
            state_token: 0,
            scope: "filt",
            group: "aggregate",
            elapsed_ms: 10, // 2× 10 = 20, well under floor
        });
        expect(o.computeDebounce("filt")).toBe(500);
    });

    it("computeDebounce respects maxDebounceMs ceiling", () => {
        const o = new StateOrchestrator({
            ws: new FakeWs(),
            minDebounceMs: 200,
            maxDebounceMs: 3000,
            multiplier: 2,
        });
        o.onStatGroupResult({
            type: "stat_group_result",
            state_token: 0,
            scope: "filt",
            group: "aggregate",
            elapsed_ms: 6000, // 2× = 12000, hits ceiling
        });
        expect(o.computeDebounce("filt")).toBe(3000);
    });

    it("initialAggregateMs seeds the baseline before any observed compute", () => {
        const o = new StateOrchestrator({
            ws: new FakeWs(),
            initialAggregateMs: { filt: 250 },
            minDebounceMs: 10,
            maxDebounceMs: 5000,
            multiplier: 2,
        });
        expect(o.computeDebounce("filt")).toBe(500); // 2× 250
        // Unrelated scope still uses fallback.
        expect(o.computeDebounce("clean")).toBe(1000); // 2× 500 (default)
    });

    it("dispose cancels all pending aggregate timers", () => {
        orch.onStateChange({ search_string: "x" });
        orch.dispose();
        jest.advanceTimersByTime(10_000);
        expect(ws.byType("compute_stat_group")).toHaveLength(0);
    });

    it("scopesForAggregate parameter overrides default ['filt']", () => {
        orch.onStateChange({ search_string: "x" }, { scopesForAggregate: ["filt", "clean"] });
        jest.advanceTimersByTime(10_000);
        const reqs = ws.byType("compute_stat_group");
        const scopes = reqs.map((r) => r.scope).sort();
        expect(scopes).toEqual(["clean", "filt"]);
    });
});
