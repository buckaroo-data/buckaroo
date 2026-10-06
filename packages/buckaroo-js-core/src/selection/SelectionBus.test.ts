import { SelectionBus, getSelectionBus } from "./SelectionBus";

describe("SelectionBus", () => {
    it("delivers a published selection to a subscriber on the same channel", () => {
        const bus = new SelectionBus("test-roundtrip");
        const received: number[][] = [];
        bus.subscribe("ch", (msg) => received.push(msg.ids as number[]));
        bus.publish("ch", [1, 2, 3], "src-A");
        expect(received).toEqual([[1, 2, 3]]);
    });

    it("filters out a subscriber's own echo via ownSource", () => {
        const bus = new SelectionBus("test-echo");
        const seenBySelf: number[][] = [];
        const seenByOther: number[][] = [];
        bus.subscribe("ch", (m) => seenBySelf.push(m.ids as number[]), "self");
        bus.subscribe("ch", (m) => seenByOther.push(m.ids as number[]), "other");
        bus.publish("ch", [7], "self");
        expect(seenBySelf).toEqual([]);
        expect(seenByOther).toEqual([[7]]);
    });

    it("does not deliver across channels", () => {
        const bus = new SelectionBus("test-channels");
        const onA: number[][] = [];
        bus.subscribe("a", (m) => onA.push(m.ids as number[]));
        bus.publish("b", [1], "src");
        expect(onA).toEqual([]);
    });

    it("getSelectionBus returns a stable singleton on window", () => {
        const a = getSelectionBus();
        const b = getSelectionBus();
        expect(a).toBe(b);
    });
});
