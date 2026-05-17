import { buckarooWsUrl } from "./BuckarooServerView";

describe("buckarooWsUrl", () => {
    it("maps http → ws", () => {
        expect(buckarooWsUrl("http://localhost:8700", "sales")).toBe("ws://localhost:8700/ws/sales");
    });

    it("maps https → wss", () => {
        expect(buckarooWsUrl("https://example.com", "sales")).toBe("wss://example.com/ws/sales");
    });

    it("preserves ws://", () => {
        expect(buckarooWsUrl("ws://localhost:8700", "sales")).toBe("ws://localhost:8700/ws/sales");
    });

    it("preserves wss://", () => {
        expect(buckarooWsUrl("wss://example.com", "sales")).toBe("wss://example.com/ws/sales");
    });

    it("includes the port in the host", () => {
        expect(buckarooWsUrl("http://10.0.0.5:9000", "s")).toBe("ws://10.0.0.5:9000/ws/s");
    });

    it("URL-encodes the session id", () => {
        expect(buckarooWsUrl("http://localhost:8700", "with space/slash")).toBe(
            "ws://localhost:8700/ws/with%20space%2Fslash",
        );
    });
});
