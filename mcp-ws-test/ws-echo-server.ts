/**
 * Minimal WebSocket echo server on port 9999.
 * Run separately: bun ws-echo-server.ts
 *
 * Sends a welcome message on connect, echoes everything back.
 */
import { WebSocketServer } from "ws";

const PORT = 9999;
const wss = new WebSocketServer({ port: PORT });

wss.on("listening", () => {
  console.log(`WebSocket echo server listening on ws://localhost:${PORT}`);
});

wss.on("connection", (ws) => {
  console.log("Client connected");
  ws.send(JSON.stringify({ type: "welcome", message: "WebSocket connection successful!" }));

  ws.on("message", (data) => {
    const msg = data.toString();
    console.log("Received:", msg);
    ws.send(JSON.stringify({ type: "echo", data: msg }));
  });

  ws.on("close", () => {
    console.log("Client disconnected");
  });
});
