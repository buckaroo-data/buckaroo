/**
 * A row request names the stats_gen of the state it was made for, so the
 * server can tell a reply to it from a reply to a request that predates the
 * state on screen (the push that follows rows is keyed on it).
 */
import { getKeySmartRowCache } from "./BuckarooWidgetInfinite";
import { PayloadArgs } from "./DFViewerParts/SmartRowCache";

const fakeModel = (expectedGen: number | undefined) => {
    const send = jest.fn();
    return { send, model: { send, on: jest.fn(), stats: { expectedGen } } };
};

const request = (sort?: string): PayloadArgs => ({
    sourceName: "default", start: 0, end: 50, origEnd: 50, sort, sort_direction: sort ? "desc" : undefined,
});

describe("infinite_request", () => {
    it("carries the gen the client is showing, whatever the sort", () => {
        const { send, model } = fakeModel(4);
        const cache = getKeySmartRowCache(model, jest.fn());
        cache.getRequestRows(request(), jest.fn(), jest.fn());
        cache.getRequestRows(request("b"), jest.fn(), jest.fn());
        expect(send.mock.calls.map(([msg]) => [msg.type, msg.stats_gen])).toEqual([
            ["infinite_request", 4],
            ["infinite_request", 4],
        ]);
    });

    it("carries no gen when the model has no stats channel (a Jupyter widget)", () => {
        const send = jest.fn();
        const cache = getKeySmartRowCache({ send, on: jest.fn() }, jest.fn());
        cache.getRequestRows(request(), jest.fn(), jest.fn());
        expect(send.mock.calls[0][0].stats_gen).toBeUndefined();
    });
});
