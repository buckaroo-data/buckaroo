/**
 * HeightDemo — a minimal "stacked-cell host" the way #846/#847 describes.
 *
 * Renders multiple BuckarooServerView embeds in a column, each pointing at
 * a server session whose row count is controlled via query string. Used by
 * pw-tests/server-embed-height.spec.ts to verify:
 *
 *   - With `?autoHeight=1`, each cell's grid sizes to its own row count,
 *     leaving no dead space between the rows and the cell wrapper.
 *   - Without `?autoHeight=1`, the 4-row cell's wrapper extends to its
 *     parent's full height — the bug #847 fixes.
 *
 * Sessions are loaded ahead of mount via /load (same code path as App.tsx).
 *
 * Query string format:
 *   /height-demo?sessions=small,large&autoHeight=1
 * where each name in `sessions` maps to a `(rowCount, mode)` preset below.
 */
import { useEffect, useState } from "react";
import { BuckarooServerView } from "buckaroo-js-core";

type Preset = {
  /** Session id we'll send to /load. */
  session: string;
  /** Path the server should ingest. Pre-built CSVs live under
   *  docs/examples/server-embed/data/. */
  path: string;
  /** Mode for the embedded BuckarooServerView. */
  mode: "viewer" | "buckaroo";
  /** Approx row count, used in the cell label so the test can assert it. */
  rowCount: number;
};

const PRESETS: Record<string, Preset> = {
  small: {
    session: "height-demo-small",
    path: "docs/examples/server-embed/data/height_small.csv",
    mode: "viewer",
    rowCount: 4,
  },
  large: {
    session: "height-demo-large",
    path: "docs/examples/server-embed/data/height_large.csv",
    mode: "viewer",
    rowCount: 200,
  },
};

function wsUrlFor(session: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/${encodeURIComponent(session)}`;
}

async function ensureSession(p: Preset): Promise<void> {
  // /load is idempotent on a session-id basis — calling it twice with the
  // same session just refreshes the data.
  const res = await fetch("/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session: p.session,
      path: p.path,
      mode: p.mode,
      no_browser: true,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message || body?.error || `HTTP ${res.status}`);
  }
}

export default function HeightDemo() {
  const qs = new URLSearchParams(location.search);
  const presets = (qs.get("sessions") || "small,large")
    .split(",")
    .map((k) => k.trim())
    .map((k) => PRESETS[k])
    .filter((p): p is Preset => !!p);
  const autoHeight = qs.get("autoHeight") === "1";
  const hostHeight = Number(qs.get("hostHeight") || "900");

  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await Promise.all(presets.map(ensureSession));
        if (!cancelled) setReady(true);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error)
    return (
      <pre data-testid="error" style={{ padding: 16, color: "#b00020" }}>
        {error}
      </pre>
    );
  if (!ready) return <div data-testid="loading">Loading sessions…</div>;

  return (
    <div
      data-testid="host"
      style={{
        width: 800,
        height: hostHeight,
        border: "2px solid red",
        boxSizing: "border-box",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: 8,
      }}
    >
      {presets.map((p, i) => (
        <div
          data-testid={`cell-${i}`}
          data-row-count={p.rowCount}
          key={p.session}
          style={{ border: "1px dashed #888" }}
        >
          <div style={{ fontSize: 11, padding: "2px 6px", color: "#888" }}>
            {p.session} — {p.rowCount} rows, autoHeight={String(autoHeight)}
          </div>
          <BuckarooServerView
            key={`${p.session}-${autoHeight}`}
            wsUrl={wsUrlFor(p.session)}
            autoHeight={autoHeight}
          />
        </div>
      ))}
    </div>
  );
}
