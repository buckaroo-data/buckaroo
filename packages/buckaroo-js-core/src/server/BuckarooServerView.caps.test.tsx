/**
 * BuckarooServerView — capability advertisement (rows-first c2).
 *
 * The server records a client's capabilities from `?caps=` on the WebSocket
 * URL, because it sends the first message before the client says anything. A
 * client that merges `stats_update` must put it there, whatever URL the host
 * passes in.
 */
import { render, cleanup, waitFor } from "@testing-library/react";
import { BuckarooServerView } from "./BuckarooServerView";

const capturedViewProps: any[] = [];

jest.mock("./BuckarooView", () => ({
    BuckarooView: (props: any) => {
        capturedViewProps.push(props);
        return <div data-testid="buckaroo-view-stub" />;
    },
    pickMode: (m: unknown) => (m === "buckaroo" ? "buckaroo" : "viewer"),
}));

jest.mock("./WebSocketModel", () => ({
    WebSocketModel: class { constructor(_ws: any, _state: any) {} },
}));

class FakeWebSocket {
    static instances: FakeWebSocket[] = [];
    binaryType = "arraybuffer";
    onopen: (() => void) | null = null;
    onerror: ((e: any) => void) | null = null;
    private listeners: Record<string, Set<(e: any) => void>> = {};
    constructor(public url: string) {
        FakeWebSocket.instances.push(this);
        setTimeout(() => {
            this.onopen?.();
            setTimeout(() => {
                const initial = {
                    type: "initial_state",
                    df_meta: { total_rows: 4, columns: 2, filtered_rows: 4, rows_shown: 4 },
                    df_data_dict: {},
                    df_display_args: {},
                    mode: "viewer",
                };
                this.listeners["message"]?.forEach((h) => h({ data: JSON.stringify(initial) } as any));
            }, 0);
        }, 0);
    }
    addEventListener(ev: string, h: (e: any) => void) {
        (this.listeners[ev] ??= new Set()).add(h);
    }
    removeEventListener(ev: string, h: (e: any) => void) {
        this.listeners[ev]?.delete(h);
    }
    close() {}
}

const origWebSocket = (globalThis as any).WebSocket;

beforeAll(() => {
    (globalThis as any).WebSocket = FakeWebSocket;
});
afterAll(() => {
    (globalThis as any).WebSocket = origWebSocket;
});
afterEach(() => {
    capturedViewProps.length = 0;
    FakeWebSocket.instances.length = 0;
    cleanup();
});

describe("BuckarooServerView advertises stats_update", () => {
    it("opens the socket with ?caps=stats_update", async () => {
        render(<BuckarooServerView wsUrl="ws://x/ws/s" />);
        await waitFor(() => expect(capturedViewProps.length).toBeGreaterThan(0));
        expect(FakeWebSocket.instances).toHaveLength(1);
        expect(FakeWebSocket.instances[0].url).toBe("ws://x/ws/s?caps=stats_update");
    });

    it("keeps the query string the host passed", async () => {
        render(<BuckarooServerView wsUrl="ws://x/ws/s?token=abc" />);
        await waitFor(() => expect(capturedViewProps.length).toBeGreaterThan(0));
        expect(FakeWebSocket.instances[0].url).toBe("ws://x/ws/s?token=abc&caps=stats_update");
    });
});
