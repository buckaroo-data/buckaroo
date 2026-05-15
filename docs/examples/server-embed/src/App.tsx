import { useState } from "react";
import { BuckarooServerView } from "buckaroo-js-core";
import "buckaroo-js-core/dist/style.css";

type Mode = "viewer" | "buckaroo" | "lazy";
type Preset = {
  label: string;
  session: string;
  path: string;
  mode: Mode;
  hint?: string;
};

// The `path` is read by the Buckaroo server, so it must be reachable
// from where `python -m buckaroo.server` is running (the repo root in
// the README). See README for the curl commands that download the
// "in-the-wild" parquet files into docs/examples/server-embed/data/.
const PRESETS: Preset[] = [
  {
    label: "Citi Bike, April 2016 (bundled in repo, ~10 MB)",
    session: "citibike-2016-04",
    path: "docs/example-notebooks/citibike-trips-2016-04.parq",
    mode: "buckaroo",
  },
  {
    label: "NYC Yellow Taxi, Jan 2024 (~50 MB)",
    session: "yellow-2024-01",
    path: "docs/examples/server-embed/data/yellow_tripdata_2024-01.parquet",
    mode: "buckaroo",
    hint: "download — see README",
  },
  {
    label: "NYC Green Taxi, Jan 2024 (~1.4 MB)",
    session: "green-2024-01",
    path: "docs/examples/server-embed/data/green_tripdata_2024-01.parquet",
    mode: "buckaroo",
    hint: "download — see README",
  },
  {
    label: "NYC FHV high-volume, Jan 2024 (~470 MB, ~20M rows)",
    session: "fhvhv-2024-01",
    path: "docs/examples/server-embed/data/fhvhv_tripdata_2024-01.parquet",
    mode: "buckaroo",
    hint: "download — see README",
  },
];

type Status =
  | { kind: "idle" }
  | { kind: "loading"; preset: Preset }
  | { kind: "ready"; preset: Preset; rows: number; path?: string }
  | { kind: "error"; message: string };

export default function App() {
  const [presetIdx, setPresetIdx] = useState(0);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function load() {
    const preset = PRESETS[presetIdx];
    setStatus({ kind: "loading", preset });
    try {
      const res = await fetch("/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session: preset.session,
          path: preset.path,
          mode: preset.mode,
          no_browser: true,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = body?.message || body?.error || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      setStatus({
        kind: "ready",
        preset,
        rows: body?.metadata?.rows ?? body?.rows ?? 0,
        path: body?.metadata?.filename ?? preset.path,
      });
      setActiveSession(preset.session);
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }

  // wsUrl is relative to the page origin — vite.config.ts proxies
  // /ws/* to the Buckaroo server, so the same proxy that handles
  // /load handles the WebSocket too.
  const wsUrl = activeSession
    ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/${encodeURIComponent(activeSession)}`
    : null;

  return (
    <>
      <header style={bar}>
        <label style={field}>
          Dataset
          <select
            value={presetIdx}
            onChange={(e) => setPresetIdx(Number(e.target.value))}
            style={input}
          >
            {PRESETS.map((p, i) => (
              <option key={p.session} value={i}>
                {p.label}
                {p.hint ? ` — ${p.hint}` : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={load}
          disabled={status.kind === "loading"}
          style={button}
        >
          {status.kind === "loading" ? "Loading…" : "Load"}
        </button>
        <span style={statusStyle(status)}>{statusText(status)}</span>
      </header>
      <main style={{ flex: 1, minHeight: 0 }}>
        {wsUrl ? (
          <BuckarooServerView key={wsUrl} wsUrl={wsUrl} />
        ) : (
          <div style={empty}>Pick a dataset and hit Load.</div>
        )}
      </main>
    </>
  );
}

function statusText(s: Status): string {
  switch (s.kind) {
    case "idle":
      return "";
    case "loading":
      return `loading ${s.preset.path}…`;
    case "ready":
      return `${s.path ?? s.preset.path} — ${s.rows.toLocaleString()} rows`;
    case "error":
      return `error: ${s.message}`;
  }
}

const bar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "10px 14px",
  borderBottom: "1px solid #ddd",
  background: "#f7f7f8",
};
const field: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  fontSize: 11,
  color: "#555",
  flex: 1,
  maxWidth: 540,
};
const input: React.CSSProperties = {
  padding: "4px 6px",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: 13,
};
const button: React.CSSProperties = {
  padding: "6px 14px",
  border: "1px solid #888",
  borderRadius: 4,
  background: "#fff",
  cursor: "pointer",
  fontSize: 13,
};
const empty: React.CSSProperties = {
  padding: 40,
  fontFamily: "system-ui, sans-serif",
  color: "#888",
};

function statusStyle(s: Status): React.CSSProperties {
  return {
    marginLeft: "auto",
    fontSize: 12,
    color: s.kind === "error" ? "#b00020" : "#666",
  };
}
