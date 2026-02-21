import { App } from "@modelcontextprotocol/ext-apps";

const loadingEl = document.getElementById("loading")!;
const iframeEl = document.getElementById("viewer") as HTMLIFrameElement;

const app = new App({ name: "Buckaroo Viewer", version: "0.0.1" });

app.ontoolresult = (result) => {
  const text = result.content?.find((c: any) => c.type === "text")?.text ?? "";

  // Extract session ID from the tool result text (format: "session:<id>")
  const match = text.match(/^session:(\w+)$/m);
  if (match) {
    const sessionId = match[1];
    iframeEl.src = `http://localhost:8700/s/${sessionId}`;
    iframeEl.style.display = "block";
    loadingEl.style.display = "none";
  } else {
    loadingEl.textContent = "Error: could not find session ID in tool result";
  }
};

app.connect();

// Log CSP violations for debugging
document.addEventListener("securitypolicyviolation", (e) => {
  console.warn(`CSP violation: ${e.violatedDirective} — ${e.blockedURI}`);
});
