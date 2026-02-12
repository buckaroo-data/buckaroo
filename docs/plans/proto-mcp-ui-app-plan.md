# Buckaroo MCP — Living Plan

## Implementation Status

### Done — Mode A: Claude Code (Browser Tab)

**Data Server** (`buckaroo/server/`) — Tornado HTTP + WebSocket, fully working:
- `GET /health` — returns `{"status": "ok"}`
- `POST /load` — accepts `{ session, path }`, returns `{ session, path, rows, columns: [{name, dtype}] }`
- `GET /s/<session-id>` — serves Buckaroo HTML page with standalone JS
- `WS /ws/<session-id>` — binary Parquet streaming with infinite scroll
- Browser focus via AppleScript on macOS (`buckaroo/server/focus.py`)
- Supports: CSV, TSV, Parquet, JSON
- Default port: 8888 (configurable via `--port`)
- Start: `python -m buckaroo.server [--port PORT] [--no-browser]`

**MCP Tool** (`buckaroo/mcp_tool.py`) — FastMCP stdio server, ~70 lines:
- `view_data(path: str)` — the only tool, one string argument
- Auto-starts data server if not running (health check → spawn → poll)
- Session isolation via per-process UUID (`SESSION_ID`)
- Returns text summary to LLM: row count, column names/dtypes, interactive URL
- Uses only stdlib HTTP (`urllib.request`) — no extra deps beyond `mcp`

**Packaging** (`pyproject.toml`):
- Optional dep group: `mcp = ["mcp"]` — install with `pip install buckaroo[mcp]`
- Console script: `buckaroo-table = "buckaroo.mcp_tool:main"`
- Claude Code config: `.mcp.json` in project root

**How to use:**
1. `uv sync --extra mcp`
2. Restart Claude Code — `buckaroo-table` appears as MCP server
3. Ask Claude to view a CSV/Parquet file — auto-starts server, opens browser, returns summary

### Not Yet Done

- Mode B: Claude Desktop iframe (see architecture below)
- `updateModelContext` for LLM awareness of user's view state
- Idle timeout / server shutdown
- Multiple files per session (tabbed UI)
- PyPI distribution as standalone package

---

## What We Proved (2026-02-12)

### MCP App iframe renders in Claude Desktop
- Claude Desktop must be in **chat mode** (not code mode) — `sidebarMode: "chat"` in config
- Server must be **stdio-only** — any stdout output (like `console.log`) corrupts the JSON-RPC transport and crashes the connection
- Use `registerAppTool` + `registerAppResource` from `@modelcontextprotocol/ext-apps/server`
- HTML must use `App` class from `@modelcontextprotocol/ext-apps` and call `app.connect()` — without this the host won't render the iframe
- Vite + `vite-plugin-singlefile` bundles everything into one self-contained HTML file

### localhost WebSocket works from inside the iframe
- The iframe in Claude Desktop CAN connect to `ws://localhost:<port>`
- We declared `connectDomains: ["ws://localhost:9999", "http://localhost:9999"]` in CSP metadata
- The echo server received the connection, sent a welcome message, and the iframe displayed it
- This means **Option B (direct WebSocket data transport) is viable** — same architecture as Jupyter

### Test app location
- Working test app: `/Users/paddy/buckaroo/mcp-ws-test/`
- Key files: `server.ts`, `main.ts`, `src/mcp-app.ts`, `mcp-app.html`
- Echo server: `ws-echo-server.ts` (port 9999)
- Build: `npm run build:html`, run echo server: `npm run ws-server`
- Claude Desktop config: `~/Library/Application Support/Claude/claude_desktop_config.json`

---

## Two Deployment Modes, One Codebase

The Buckaroo data server and Buckaroo JS client share the same codebase regardless of how they're deployed. There are two modes:

### Mode A: Claude Code (CLI) — Browser Tab
For terminal-based workflows. The MCP tool pings a local server, which pushes updates to an open browser tab.

### Mode B: Claude Desktop — MCP App iframe
For Claude Desktop's embedded UI. The tool returns an inline HTML resource rendered in an iframe that connects back to the local server.

**What's shared across both modes:**
- Python data server (WebSocket protocol, DataFrame loading, Parquet serialization)
- Buckaroo JS client (React, AG-Grid, SmartRowCache, hyparquet)
- MCP tool definition (`view_data`)
- Same WebSocket row-fetching protocol

**What differs:**

|  | Mode A: Browser Tab (Claude Code) | Mode B: Iframe (Claude Desktop) |
|---|---|---|
| **Client** | Normal browser tab at `localhost:<port>` | iframe inside Claude Desktop |
| **How HTML is served** | Server serves the page over HTTP | Inlined into `ui://` resource (single-file bundle) |
| **How load is triggered** | HTTP POST `/load` from MCP server | Via MCP App tool result / `app.ontoolresult` |
| **Browser focus** | AppleScript to bring tab to front (macOS) | N/A (embedded) |
| **LLM context updates** | Return text summary in tool result | `app.updateModelContext()` |
| **Server instance** | Standalone long-running process | Could be same or separate instance |

---

## Architecture: Mode A (Claude Code — Browser Tab)

This is the primary target. Simpler, works with any MCP client, full browser experience.

```
Claude Code CLI
  │
  │  calls view_data(path="/tmp/pipeline_output.parquet")
  │  (just a file path string — zero data tokens)
  ▼
Buckaroo MCP Server (Python, stdio, launched by Claude Code)
  │
  │  1. Health check: GET localhost:<port>/health
  │  2. If no server running → spawn buckaroo-server as background process
  │  3. POST localhost:<port>/load { session: "<id>", path: "/tmp/pipeline_output.parquet" }
  │  4. On first call: webbrowser.open("localhost:<port>/s/<session-id>")
  │  5. On subsequent calls: AppleScript to focus the existing tab
  │  6. Returns text summary to LLM: "Opened orders.parquet (1.2M rows, 15 columns) in Buckaroo viewer"
  ▼
Buckaroo Local Server (Python, separate long-running process)
  │
  │  Receives /load → loads DataFrame → pushes to browser via WebSocket
  ▼
Browser Tab (localhost:<port>/s/<session-id>)
  │
  │  WebSocket connects to ws://localhost:<port>/ws/<session-id>
  │  Receives "load" push → fetches rows on demand
  │  infinite scroll, sort, filter — all over WebSocket
```

### Why this works
- LLM never serializes tabular data — just passes a file path string
- Data transport is direct WebSocket between the local server and browser — no middleman
- The local server reads CSV/JSON/Parquet from disk and streams row slices over WebSocket
- Same architecture Buckaroo already uses in Jupyter (anywidget binary messages → WebSocket)
- Works with **any** MCP client — not tied to Claude Desktop

### Server auto-start
The MCP server handles lifecycle automatically:
1. On first `view_data` call, check `GET localhost:<port>/health`
2. If no response → `subprocess.Popen(["buckaroo-server", "--port", str(port)])` as a detached background process
3. Poll `/health` until ready (brief startup delay, ~1-2s)
4. Server stays running after MCP server exits — survives across Claude Code sessions
5. Subsequent sessions reuse the already-running server

### Session isolation (concurrent Claude Code sessions)
Multiple Claude Code sessions can run simultaneously without cross-talk:

```
Session 1 (Claude Code)                    Session 2 (Claude Code)
  │ view_data("orders.parquet")              │ view_data("customers.parquet")
  ▼                                          ▼
MCP Server (session=abc)                   MCP Server (session=def)
  │ POST /load {session:"abc",               │ POST /load {session:"def",
  │   path:"orders.parquet"}                 │   path:"customers.parquet"}
  ▼                                          ▼
  └──────────► Shared Buckaroo Server ◄──────┘
               (single process, one port)
                │                  │
                ▼                  ▼
Browser Tab                    Browser Tab
localhost:8888/s/abc           localhost:8888/s/def
  → shows "orders"              → shows "customers"
```

- Each MCP server instance generates a UUID session ID on startup (persists for the Claude Code conversation)
- Session ID is included in `/load` POST and browser URL
- WebSocket connections are scoped by session — server routes messages to the correct tab
- One shared server process, many isolated sessions

### Browser focus (macOS)
On subsequent `view_data` calls, the MCP server asks the local server to focus the correct tab. The server runs AppleScript:

```applescript
tell application "Google Chrome"
    activate
    repeat with w in windows
        set i to 0
        repeat with t in tabs of w
            set i to i + 1
            if URL of t contains "localhost:8888/s/<session-id>" then
                set active tab index of w to i
                set index of w to 1
                return
            end if
        end repeat
    end repeat
end tell
```

- Triggered by the server on `/load`, not by the MCP server (the server has system access)
- First call uses `webbrowser.open()` (auto-focuses new tab)
- Subsequent calls use AppleScript to find and focus the existing tab by URL
- macOS only — on other platforms, skip focus (tab still updates via WebSocket)
- Could detect browser (Chrome, Safari, Arc) or make it configurable

---

## Architecture: Mode B (Claude Desktop — MCP App iframe)

Same data server, but the client is an inline HTML resource rendered inside Claude Desktop.

```
Claude LLM
  │
  │  calls view_data(path="/tmp/pipeline_output.parquet")
  ▼
Buckaroo MCP Server (Python, stdio, launched by Claude Desktop)
  │
  │  1. Ensure local server is running (same auto-start as Mode A)
  │  2. POST /load to the server
  │  3. Returns ui:// resource with Buckaroo JS inlined (single-file HTML)
  ▼
Iframe (Buckaroo JS, rendered by Claude Desktop)
  │
  │  connects ws://localhost:<port> directly
  │  infinite scroll, sort, filter — all over WebSocket
```

Key differences from Mode A:
- HTML + JS must be bundled into a single file (`vite-plugin-singlefile`) since `ui://` resources are self-contained
- Uses `@modelcontextprotocol/ext-apps` App class + `app.connect()`
- CSP metadata must declare `connectDomains` for `ws://localhost:<port>`
- Can use `app.updateModelContext()` to feed view state back to the LLM

---

## Tool Design

### Model-facing tool (what the LLM calls)

```json
{
  "name": "view_data",
  "description": "Display a tabular data file in an interactive Buckaroo viewer. Supports CSV, JSON, and Parquet files. Use this after generating data pipeline output to let the user explore results interactively.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Absolute path to a CSV, JSON, or Parquet file"
      }
    },
    "required": ["path"]
  }
}
```

One tool. One string argument. That's it.

### Tool result (Mode A — Claude Code)
The tool returns a text summary for the LLM (no data, just metadata):
```
Opened sales.parquet in Buckaroo viewer (browser tab).
1,234,567 rows × 15 columns.
Columns: order_id (int), customer_name (str), amount (float), date (datetime), ...
```

This gives the LLM enough context to discuss the data without consuming tokens on the actual rows.

---

## WebSocket Protocol (shared by both modes)

The Buckaroo data server handles these messages from the browser client:

| Message | Purpose | Response |
|---------|---------|----------|
| `{ type: "load", path: "/foo/bar.parquet" }` | Load a file | `{ type: "metadata", schema, rowCount, columns }` |
| `{ type: "get_rows", start, end, sort?, filters? }` | Fetch a slice of rows | `{ type: "rows", start, end, data }` (binary Parquet or JSON) |
| `{ type: "get_stats" }` | Column-level summary stats | `{ type: "stats", columns: {...} }` |

In Mode A, the server can also **push** a load command to the browser when it receives a `/load` POST — the browser doesn't need to initiate the load itself.

The JS client handles all rendering, caching (SmartRowCache), and interaction. Same code path as Jupyter.

---

## Server HTTP Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check — returns 200 if server is running |
| `/load` | POST | Load a file for a session: `{ session, path }` |
| `/s/<session-id>` | GET | Serve the Buckaroo HTML page for a session (Mode A only) |
| `/ws/<session-id>` | WS | WebSocket endpoint scoped to a session |
| `/focus` | POST | Focus the browser tab for a session (triggers AppleScript on macOS) |

---

## Resolved Decisions

1. **MCP server language** — All Python. MCP tool uses FastMCP (Python MCP SDK), data server is Tornado. ✅
2. **Parquet binary transfer** — Working. Two-frame WebSocket protocol (JSON text + binary Parquet). ✅
3. **JS bundle strategy** — Mode A serves static files from `buckaroo/static/`. Mode B will need `vite-plugin-singlefile`.
4. **Python packaging** — Optional dep group in `buckaroo` package: `pip install buckaroo[mcp]`. Console script `buckaroo-table`. For PyPI standalone distribution, TBD.

## Open Questions / Next Steps

### 1. updateModelContext for LLM awareness (Mode B)
- The iframe can call `app.updateModelContext()` to tell the LLM what the user is seeing
- e.g., "User is viewing rows 50,000-50,050 of sales.parquet, sorted by revenue desc, filtered to state=CA (12,340 matches)"
- This enables the LLM to react: "I see you filtered to CA, want me to drill into that subset?"
- Design this carefully — don't spam context updates on every scroll

### 2. Multiple files per session
- Each `view_data` call within a session could replace the current view or open a new tab/panel
- Simplest: replace current view (one file per session at a time)
- Future: tabbed interface within the Buckaroo page (multiple files, user switches between them)

### 3. Server shutdown
- The data server is a long-lived background process — when does it stop?
- Options: idle timeout (stop after N minutes with no WebSocket connections), explicit `buckaroo-server stop` command, or just leave it running until the user kills it
- Leaning toward idle timeout with a generous default (e.g., 30 minutes)

### 4. PyPI standalone distribution
- Currently in-tree as part of `buckaroo` package
- For wider distribution: `buckaroo-mcp` on PyPI, `uvx buckaroo-mcp`
- Claude Desktop config: `{ "command": "uvx", "args": ["buckaroo-mcp"] }`
