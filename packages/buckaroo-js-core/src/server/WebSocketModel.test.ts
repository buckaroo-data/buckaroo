/**
 * WebSocketModel — state-change sequencing (#998).
 *
 * Each buckaroo_state_change the model sends carries an incrementing
 * `state_seq`. The server echoes it as `reply_seq` on the `initial_state`
 * it sends back to the originating client. A reply whose `reply_seq` is
 * older than the latest change this model sent is stale and must not be
 * applied; otherwise the reply for "alle" lands after "allen" was sent
 * and sets the client's buckaroo_state back. Replies with no `reply_seq`
 * (another tab's change, a /load push, a fresh connection) still apply.
 */
import { WebSocketModel } from "./WebSocketModel";

class FakeWebSocket {
    readyState = WebSocket.OPEN;
    sent: any[] = [];
    onmessage: ((event: MessageEvent) => void) | null = null;
    send(data: string) {
        this.sent.push(JSON.parse(data));
    }
    deliver(msg: Record<string, any>) {
        this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
    }
}

const stateWithSearch = (search: string) => ({
    post_processing: "",
    cleaning_method: "",
    quick_command_args: { search },
    df_display: "main",
    show_commands: false,
    sampled: false,
    search_string: search,
});

function makeModel() {
    const ws = new FakeWebSocket();
    const model = new WebSocketModel(ws as unknown as WebSocket, {
        buckaroo_state: stateWithSearch(""),
        df_meta: { total_rows: 1 },
    });
    const changes: any[] = [];
    model.on("change:buckaroo_state", (v: any) => changes.push(v));
    return { ws, model, changes };
}

function sendSearch(model: WebSocketModel, search: string) {
    model.set("buckaroo_state", stateWithSearch(search));
    model.save_changes();
}

describe("WebSocketModel state_seq (#998)", () => {
    it("attaches an incrementing state_seq to each buckaroo_state_change", () => {
        const { ws, model } = makeModel();
        sendSearch(model, "a");
        sendSearch(model, "al");
        expect(ws.sent.map((m) => m.type)).toEqual(["buckaroo_state_change", "buckaroo_state_change"]);
        expect(ws.sent.map((m) => m.state_seq)).toEqual([1, 2]);
        expect(ws.sent[1].new_state.quick_command_args.search).toBe("al");
    });

    it("drops an initial_state whose reply_seq is older than the latest sent seq", () => {
        const { ws, model, changes } = makeModel();
        sendSearch(model, "a");
        sendSearch(model, "al");
        changes.length = 0;

        ws.deliver({
            type: "initial_state",
            reply_seq: 1,
            buckaroo_state: stateWithSearch("a"),
            df_meta: { total_rows: 10 },
        });
        expect(model.get("buckaroo_state").quick_command_args.search).toBe("al");
        expect(model.get("df_meta")).toEqual({ total_rows: 1 });
        expect(changes).toEqual([]);

        ws.deliver({
            type: "initial_state",
            reply_seq: 2,
            buckaroo_state: stateWithSearch("al"),
            df_meta: { total_rows: 3 },
        });
        expect(model.get("buckaroo_state").quick_command_args.search).toBe("al");
        expect(model.get("df_meta")).toEqual({ total_rows: 3 });
        expect(changes).toHaveLength(1);
    });

    it("applies an initial_state that carries no reply_seq", () => {
        const { ws, model, changes } = makeModel();
        sendSearch(model, "a");
        sendSearch(model, "al");
        changes.length = 0;

        ws.deliver({
            type: "initial_state",
            buckaroo_state: stateWithSearch(""),
            df_meta: { total_rows: 5 },
        });
        expect(model.get("buckaroo_state").quick_command_args.search).toBe("");
        expect(model.get("df_meta")).toEqual({ total_rows: 5 });
        expect(changes).toHaveLength(1);
    });
});
