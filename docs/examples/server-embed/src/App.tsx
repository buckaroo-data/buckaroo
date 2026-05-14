import { useMemo, useState } from "react";
import { BuckarooServerView, buckarooWsUrl } from "buckaroo-js-core";
import "buckaroo-js-core/dist/style.css";

type Metadata = { path?: string; rows?: number; [k: string]: unknown };

export default function App() {
  const [serverUrl, setServerUrl] = useState("http://localhost:8700");
  const [sessionId, setSessionId] = useState("demo");
  const [committed, setCommitted] = useState({ serverUrl, sessionId });
  const [metadata, setMetadata] = useState<Metadata | null>(null);

  const wsUrl = useMemo(
    () => buckarooWsUrl(committed.serverUrl, committed.sessionId),
    [committed]
  );

  return (
    <>
      <header style={bar}>
        <label style={field}>
          Server
          <input
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            style={input}
          />
        </label>
        <label style={field}>
          Session
          <input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            style={input}
          />
        </label>
        <button
          onClick={() => {
            setMetadata(null);
            setCommitted({ serverUrl, sessionId });
          }}
          style={button}
        >
          Connect
        </button>
        <span style={status}>
          {metadata
            ? `${metadata.path ?? "(no path)"} — ${metadata.rows ?? "?"} rows`
            : `connecting to ${wsUrl}`}
        </span>
      </header>
      <main style={{ flex: 1, minHeight: 0 }}>
        <BuckarooServerView wsUrl={wsUrl} onMetadata={setMetadata} />
      </main>
    </>
  );
}

const bar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "10px 14px",
  borderBottom: "1px solid #ddd",
  background: "#f7f7f8",
};
const field: React.CSSProperties = { display: "flex", flexDirection: "column", fontSize: 11, color: "#555" };
const input: React.CSSProperties = { padding: "4px 6px", border: "1px solid #ccc", borderRadius: 4, fontSize: 13, minWidth: 220 };
const button: React.CSSProperties = { padding: "6px 14px", border: "1px solid #888", borderRadius: 4, background: "#fff", cursor: "pointer", fontSize: 13 };
const status: React.CSSProperties = { marginLeft: "auto", fontSize: 12, color: "#666" };
