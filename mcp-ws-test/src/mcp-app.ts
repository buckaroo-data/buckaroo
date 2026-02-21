import { App } from "@modelcontextprotocol/ext-apps";

const resultEl = document.getElementById("result")!;
const wsStatusEl = document.getElementById("ws-status")!;

const app = new App({ name: "Hello App", version: "0.0.1" });

app.ontoolresult = (result) => {
  const text = result.content?.find((c: any) => c.type === "text")?.text;
  resultEl.textContent = text ?? "No text in result";
};

app.connect();

// WebSocket test
const WS_URL = "ws://localhost:9999";

try {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsStatusEl.textContent = "CONNECTED to ws://localhost:9999";
    wsStatusEl.className = "ws-ok";
  };

  ws.onmessage = (event) => {
    wsStatusEl.textContent += "\nReceived: " + event.data;
  };

  ws.onerror = () => {
    wsStatusEl.textContent = "FAILED — WebSocket blocked or refused";
    wsStatusEl.className = "ws-fail";
  };

  ws.onclose = (event) => {
    if (wsStatusEl.className !== "ws-ok") {
      wsStatusEl.textContent = `FAILED — closed (code=${event.code})`;
      wsStatusEl.className = "ws-fail";
    }
  };
} catch (e: any) {
  wsStatusEl.textContent = `BLOCKED — ${e.message}`;
  wsStatusEl.className = "ws-fail";
}

document.addEventListener("securitypolicyviolation", (e) => {
  wsStatusEl.textContent = `CSP BLOCKED: ${e.violatedDirective} — ${e.blockedURI}`;
  wsStatusEl.className = "ws-fail";
});
