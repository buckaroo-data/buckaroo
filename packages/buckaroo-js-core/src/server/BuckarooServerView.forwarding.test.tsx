/**
 * BuckarooServerView — autoHeight forwarding (#846).
 *
 * Pins the one-line spread at BuckarooServerView.tsx that forwards
 * `autoHeight` to BuckarooView. Without this test, a future refactor that
 * destructures the prop but forgets to forward it would silently regress.
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
            // Defer message delivery so BuckarooServerView's second
            // `await new Promise(...)` can register its listener first.
            setTimeout(() => {
                const initial = {
                    type: "initial_state",
                    df_meta: { total_rows: 4, columns: 2, filtered_rows: 4, rows_shown: 4 },
                    df_data_dict: {},
                    df_display_args: {
                        main: {
                            df_viewer_config: { pinned_rows: [], left_col_configs: [], column_config: [] },
                            summary_stats_key: "all_stats",
                        },
                    },
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

describe("BuckarooServerView autoHeight forwarding (#846)", () => {
    it("forwards autoHeight=true to BuckarooView", async () => {
        render(<BuckarooServerView wsUrl="ws://x/ws/s" autoHeight />);
        await waitFor(() => expect(capturedViewProps.length).toBeGreaterThan(0));
        expect(capturedViewProps[capturedViewProps.length - 1].autoHeight).toBe(true);
    });

    it("forwards autoHeight=undefined to BuckarooView when the prop is omitted", async () => {
        render(<BuckarooServerView wsUrl="ws://x/ws/s" />);
        await waitFor(() => expect(capturedViewProps.length).toBeGreaterThan(0));
        expect(capturedViewProps[capturedViewProps.length - 1].autoHeight).toBeUndefined();
    });
});
