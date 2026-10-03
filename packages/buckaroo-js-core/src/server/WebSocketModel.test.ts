/**
 * WebSocketModel — stale initial_state handling (#998).
 *
 * Every buckaroo_state_change that touches a dataflow field makes the
 * server rerun the dataflow and broadcast an initial_state. When a second
 * change goes out before the first reply comes back, the first reply must
 * not revert buckaroo_state to the older change.
 */
import { WebSocketModel } from "./WebSocketModel";
import { getKeySmartRowCache } from "../components/BuckarooWidgetInfinite";
import { PayloadArgs } from "../components/DFViewerParts/SmartRowCache";
import { BuckarooState } from "../components/WidgetTypes";

// Stand-in for the browser WebSocket: records what the model sends and lets
// a test push text and binary frames into the model's onmessage.
class FakeWebSocket {
    readyState = WebSocket.OPEN;
    sent: Record<string, any>[] = [];
    onmessage: ((ev: MessageEvent) => void) | null = null;
    onSend: ((msg: Record<string, any>) => void) | null = null;

    send(data: string): void {
        const msg = JSON.parse(data);
        this.sent.push(msg);
        this.onSend?.(msg);
    }
    sentOfType(type: string): Record<string, any>[] {
        return this.sent.filter((m) => m.type === type);
    }
    deliver(msg: Record<string, any>): void {
        this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
    }
    deliverBinary(buf: ArrayBuffer): void {
        this.onmessage?.({ data: buf } as MessageEvent);
    }
}

const BASE_STATE: BuckarooState = {
    cleaning_method: "",
    post_processing: "",
    quick_command_args: {},
    df_display: "main",
    show_commands: false,
    sampled: false,
};
const searchState = (term: string): BuckarooState => ({
    ...BASE_STATE,
    quick_command_args: { search: [term] },
});
const STATE_A = searchState("alle");
const STATE_B = searchState("allen");

const METADATA = { path: "x.parquet", rows: 3, columns: ["a"] };

// What the server broadcasts after applying `bstate`
// (buckaroo/server/session.py build_state_message). df_data_dict carries a
// marker so a test can tell which reply was applied.
const initialStateFor = (bstate: BuckarooState, extra: Record<string, any> = {}): Record<string, any> => ({
    type: "initial_state",
    protocol_version: 1,
    metadata: METADATA,
    prompt: "",
    df_display_args: {},
    df_data_dict: { marker: [{ term: String(bstate.quick_command_args.search?.[0] ?? "") }] },
    df_meta: { total_rows: 3 },
    mode: "buckaroo",
    buckaroo_state: { ...bstate, search_string: "" },
    buckaroo_options: {},
    command_config: {},
    operation_results: {},
    operations: [],
    ...extra,
});

const appliedTerm = (model: WebSocketModel): string => model.get("df_data_dict").marker[0].term;
const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

const makeModel = (bstate: BuckarooState = BASE_STATE): [FakeWebSocket, WebSocketModel] => {
    const ws = new FakeWebSocket();
    const model = new WebSocketModel(ws as unknown as WebSocket, initialStateFor(bstate));
    return [ws, model];
};

const sendChange = (model: WebSocketModel, bstate: BuckarooState): void => {
    model.set("buckaroo_state", bstate);
    model.save_changes();
};

describe("WebSocketModel initial_state while a buckaroo_state_change is outstanding", () => {
    it("drops the reply to an older change and applies the reply to the latest one", () => {
        const [ws, model] = makeModel();
        sendChange(model, STATE_A);
        sendChange(model, STATE_B);
        expect(ws.sentOfType("buckaroo_state_change").map((m) => m.new_state.quick_command_args))
            .toEqual([STATE_A.quick_command_args, STATE_B.quick_command_args]);

        const onBState = jest.fn();
        const onDfDataDict = jest.fn();
        model.on("change:buckaroo_state", onBState);
        model.on("change:df_data_dict", onDfDataDict);

        // Reply to A arrives after B was sent: stale, must not revert B.
        ws.deliver(initialStateFor(STATE_A));
        expect(model.get("buckaroo_state").quick_command_args).toEqual(STATE_B.quick_command_args);
        expect(onBState).not.toHaveBeenCalled();
        expect(onDfDataDict).not.toHaveBeenCalled();

        // Reply to B is the one we are waiting for.
        ws.deliver(initialStateFor(STATE_B));
        expect(onBState).toHaveBeenCalledTimes(1);
        expect(onDfDataDict).toHaveBeenCalledTimes(1);
        expect(model.get("buckaroo_state").quick_command_args).toEqual(STATE_B.quick_command_args);
        expect(appliedTerm(model)).toBe("allen");
    });
});

/**
 * Row cache interaction (#998, "Row cache interaction" section).
 *
 * The server answers an infinite_request from the dataflow's current state
 * and never reads sourceName, so a row request the client sends while its
 * buckaroo_state is reverted gets answered from the newer state and cached
 * under the older key. The fake server below processes messages in order,
 * as the Tornado handler does, and queues its replies so the test controls
 * when they reach the model.
 */
type DataflowTerm = string;

class FakeServer {
    state: BuckarooState = BASE_STATE;
    private replies: Array<() => void> = [];

    constructor(private ws: FakeWebSocket) {
        ws.onSend = (msg) => this.receive(msg);
    }

    private term(): DataflowTerm {
        return String(this.state.quick_command_args.search?.[0] ?? "");
    }

    private receive(msg: Record<string, any>): void {
        if (msg.type === "buckaroo_state_change") {
            this.state = msg.new_state;
            const snapshot = this.state;
            this.replies.push(() => this.ws.deliver(initialStateFor(snapshot)));
        } else if (msg.type === "infinite_request") {
            const pa: PayloadArgs = msg.payload_args;
            const term = this.term();
            const rows = [];
            for (let i = pa.start; i < Math.min(pa.end, METADATA.rows); i++) {
                rows.push({ index: i, a: `${term}-${i}` });
            }
            const resp = {
                type: "infinite_resp",
                key: pa,
                length: METADATA.rows,
                payload: { format: "json", data: rows },
            };
            this.replies.push(() => {
                this.ws.deliver(resp);
                this.ws.deliverBinary(new ArrayBuffer(0));
            });
        }
    }

    // Deliver every queued reply in order, including replies to requests
    // the client issues while earlier replies are being applied.
    async flush(): Promise<void> {
        while (this.replies.length > 0) {
            const next = this.replies.shift()!;
            next();
            await tick();
        }
    }
}

const sourceNameFor = (bstate: BuckarooState): string => JSON.stringify(bstate.quick_command_args);
const rowRequestFor = (bstate: BuckarooState): PayloadArgs => ({
    sourceName: sourceNameFor(bstate),
    start: 0,
    end: METADATA.rows,
    origEnd: METADATA.rows,
});

describe("WebSocketModel and KeyAwareSmartRowCache", () => {
    it("never caches rows from a newer dataflow under an older change's key", async () => {
        const [ws, model] = makeModel();
        const server = new FakeServer(ws);
        const src = getKeySmartRowCache(model, () => {});

        // Stand-in for the widget: a buckaroo_state change purges the grid
        // and requests the first block under a sourceName derived from the
        // dataflow fields (gridUtils.ts getDs). That happens on the React
        // render after the change, so after save_changes has sent it.
        model.on("change:buckaroo_state", (bstate: BuckarooState) => {
            setTimeout(() => src.getRequestRows(rowRequestFor(bstate), () => {}, () => {}), 0);
        });

        // Two keystrokes before any reply comes back (#998 step 1).
        sendChange(model, STATE_A);
        await tick();
        sendChange(model, STATE_B);
        await tick();
        await server.flush();

        expect(model.get("buckaroo_state").quick_command_args).toEqual(STATE_B.quick_command_args);
        // Only the request that followed the user's own change went out for A.
        const requestsForA = ws.sentOfType("infinite_request")
            .filter((m) => m.payload_args.sourceName === sourceNameFor(STATE_A));
        expect(requestsForA).toHaveLength(1);
        // Rows cached under A's key came from the A dataflow, rows under B's from B.
        expect(src.getRows(rowRequestFor(STATE_A)).map((r) => r.a)).toEqual(["alle-0", "alle-1", "alle-2"]);
        expect(src.getRows(rowRequestFor(STATE_B)).map((r) => r.a)).toEqual(["allen-0", "allen-1", "allen-2"]);
    });
});

