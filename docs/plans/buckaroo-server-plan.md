# Buckaroo Server — Implementation Plan

## Overview

A standalone Python HTTP+WebSocket server that loads tabular files and serves them to a browser-based Buckaroo UI. Used by the MCP `view_data` tool (Mode A: browser tab) and potentially the MCP App iframe (Mode B). This plan covers the server itself — the MCP shim is a separate concern.

---

## Framework: Tornado

**Why Tornado:**
- **Zero transitive dependencies** — critical for a PyPI-distributed tool. `pip install tornado` pulls in nothing else.
- **Built-in HTTP + WebSocket** — no need for a separate ASGI server (uvicorn). One `app.listen(port)` and you have both.
- **Binary WebSocket frames** — `write_message(parquet_bytes, binary=True)` is first-class. This is our primary data transport.
- **Jupyter precedent** — Jupyter's notebook server runs on Tornado. Most of our target users already have it installed. Binary data streaming over Tornado WebSockets is battle-tested in that ecosystem.
- **Self-contained testing** — `tornado.testing` provides HTTP and WebSocket test clients with zero extra test dependencies.
- **Stable, mature** — 15+ years, API stable since 6.0, asyncio-native.

**Alternatives considered:**
- FastAPI/Starlette: too many deps (pydantic, uvicorn), overkill for a local tool
- aiohttp: good but ~7 transitive deps vs Tornado's 0
- raw websockets lib: no HTTP routing, would need a second framework

---

## Server Architecture

```
buckaroo-server (single Python process)
│
├── HTTP Routes
│   ├── GET  /health              → { "status": "ok" }
│   ├── POST /load                → Load file for a session
│   ├── GET  /s/<session-id>      → Serve Buckaroo HTML page
│   └── GET  /static/...          → Serve JS/CSS assets
│
├── WebSocket
│   └── /ws/<session-id>          → Binary Parquet streaming
│
└── Session State (in-memory dict)
    └── session_id → { df, path, metadata }
```

### Endpoints

#### `GET /health`
Returns `{"status": "ok"}`. Used by MCP server to detect if buckaroo-server is already running.

#### `POST /load`
Body: `{ "session": "abc-123", "path": "/tmp/orders.parquet" }`

1. Read file at `path` into a DataFrame (Pandas or Polars, auto-detect format by extension)
2. Store in session state: `sessions[session_id] = { df, path, metadata }`
3. If a WebSocket client is connected for this session, push a `{ type: "metadata", ... }` message to trigger the browser to reload
4. Optionally focus the browser tab (macOS AppleScript)
5. Return `{ "session": "abc-123", "rows": 1234567, "columns": [...], "path": "/tmp/orders.parquet" }`

#### `GET /s/<session-id>`
Serve the Buckaroo HTML page. The session ID is embedded in the page (or read from the URL) so the JS knows which WebSocket endpoint to connect to.

#### `WS /ws/<session-id>`
Binary WebSocket endpoint. Handles the same protocol as the existing Jupyter widget:

**Client → Server (text frames, JSON):**
```json
{ "type": "infinite_request", "payload_args": { "start": 0, "end": 100, "sort": "col", "sort_direction": "asc", "second_request": {...} } }
```

**Server → Client (text frame + binary frame):**
```json
{ "type": "infinite_resp", "key": {/*echo of payload_args*/}, "data": [], "length": 50000 }
```
Immediately followed by a binary frame containing the Parquet-encoded slice.

**Server → Client push (on `/load`):**
```json
{ "type": "metadata", "path": "/tmp/orders.parquet", "rows": 1234567, "columns": [...] }
```
Plus initial state (df_display_args, df_data_dict, df_meta) so the browser can render the chrome.

---

## Session State

```python
sessions: dict[str, SessionState] = {}

@dataclass
class SessionState:
    session_id: str
    path: str
    df: pd.DataFrame          # the loaded DataFrame
    metadata: dict             # row count, column names/types
    ws_clients: set[WebSocketHandler]  # connected browser tabs
    df_display_args: dict      # column configs, viewer config
    df_data_dict: dict         # stats data (all_stats, etc.)
    df_meta: dict              # total_rows, etc.
```

On `/load`, the server reuses the existing `BuckarooInfiniteWidget` dataflow pipeline to compute `df_display_args`, `df_data_dict`, and `df_meta` — same analysis/stats/styling that Jupyter gets. The dataflow is run headless (no widget, just the pipeline).

---

## Binary WebSocket Protocol

The existing Jupyter widget sends responses as: JSON message + binary buffer (packaged together by anywidget). Over raw WebSocket, we need a convention:

**Option chosen: two-frame sequence**
1. Text frame: JSON metadata (`{ type: "infinite_resp", key: {...}, data: [], length: N }`)
2. Binary frame: Parquet bytes

The JS client pairs them: when it receives a text frame of type `infinite_resp`, it waits for the next binary frame and treats it as the buffer.

This maps directly to the existing `model.on("msg:custom", (msg, buffers) => {...})` pattern — `msg` is the JSON, `buffers[0]` is the binary frame.

**Why two frames instead of one packed message:**
- Simpler to implement on both sides
- No custom framing/length-prefix logic
- Text frames are human-readable for debugging
- Matches the existing anywidget mental model

---

## What Changes in JS

The existing JS code talks through anywidget's `model` interface:
- `model.send(json)` → send request
- `model.on("msg:custom", (msg, buffers) => {...})` → receive response
- `model.get("df_display_args")` → read widget traits (initial state)

We need a **WebSocket adapter** that implements this same interface over raw WebSocket. This is a thin shim (~50 lines):

### New file: `packages/buckaroo-js-core/src/WebSocketModel.ts`

```typescript
export class WebSocketModel {
    private ws: WebSocket;
    private pendingMsg: any = null;  // JSON frame waiting for its binary pair
    private handlers: Map<string, Function[]> = new Map();
    private state: Record<string, any>;  // initial state from server

    constructor(url: string, initialState: Record<string, any>) {
        this.state = initialState;
        this.ws = new WebSocket(url);
        this.ws.binaryType = "arraybuffer";

        this.ws.onmessage = (event) => {
            if (typeof event.data === "string") {
                // Text frame — JSON metadata
                const msg = JSON.parse(event.data);
                if (msg.type === "infinite_resp") {
                    this.pendingMsg = msg;
                    // Wait for binary frame
                } else if (msg.type === "metadata") {
                    // Server push — new file loaded
                    this.emit("metadata", msg);
                }
            } else {
                // Binary frame — Parquet bytes, pair with pending JSON
                if (this.pendingMsg) {
                    const buffers = [new DataView(event.data)];
                    this.emit("msg:custom", this.pendingMsg, buffers);
                    this.pendingMsg = null;
                }
            }
        };
    }

    send(msg: any) {
        this.ws.send(JSON.stringify(msg));
    }

    get(key: string) {
        return this.state[key];
    }

    on(event: string, handler: Function) {
        if (!this.handlers.has(event)) this.handlers.set(event, []);
        this.handlers.get(event)!.push(handler);
    }

    off(event: string, handler: Function) {
        const list = this.handlers.get(event);
        if (list) this.handlers.set(event, list.filter(h => h !== handler));
    }

    private emit(event: string, ...args: any[]) {
        (this.handlers.get(event) || []).forEach(h => h(...args));
    }
}
```

### New file: `packages/buckaroo-js-core/src/standalone.tsx`

Entry point for the browser-tab mode. Replaces `widget.tsx`:

```typescript
import { WebSocketModel } from "./WebSocketModel";
import { getKeySmartRowCache } from "./components/BuckarooWidgetInfinite";
import { DFViewerInfiniteDS } from "./components/BuckarooWidgetInfinite";

// Read session ID from URL: /s/<session-id>
const sessionId = window.location.pathname.split("/s/")[1];
const wsUrl = `ws://${window.location.host}/ws/${sessionId}`;

// Server sends initial state as first message after WS connect
// Then we create the model adapter and render
```

This entry point:
1. Extracts session ID from URL
2. Connects WebSocket
3. Receives initial state (df_display_args, df_data_dict, df_meta) from server
4. Creates `WebSocketModel` with that state
5. Passes it to `getKeySmartRowCache()` — **same function, no changes**
6. Renders `DFViewerInfiniteDS` — **same component, no changes**

### What does NOT change
- `SmartRowCache.ts` — untouched, doesn't know about transport
- `BuckarooWidgetInfinite.tsx` — untouched, `getKeySmartRowCache()` just needs a `model` with `.send()` and `.on()`
- `DFViewerInfinite.tsx` — untouched
- `gridUtils.ts` — untouched
- hyparquet usage — untouched

The existing code is already transport-agnostic through the `model` interface. We just provide a new implementation of that interface.

### Build

New esbuild (or Vite) entry point that bundles `standalone.tsx` → `standalone.js`. Served by the Tornado server as a static file. No single-file inlining needed (that's only for Mode B iframe).

---

## HTML Page

Minimal HTML served at `/s/<session-id>`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Buckaroo</title>
    <link rel="stylesheet" href="/static/compiled.css">
    <style>
        html, body, #root { margin: 0; padding: 0; width: 100%; height: 100vh; }
    </style>
</head>
<body>
    <div id="root"></div>
    <script src="/static/standalone.js"></script>
</body>
</html>
```

The session ID is in the URL path, not baked into the HTML. The JS reads it from `window.location.pathname`. This means the HTML is static and cacheable — the same file works for every session.

---

## Data Loading Pipeline

When `/load` is called, the server needs to:

1. **Read the file** into a DataFrame based on extension:
   - `.csv` → `pd.read_csv(path)`
   - `.parquet` → `pd.read_parquet(path)`
   - `.json` → `pd.read_json(path)`
   - `.tsv` → `pd.read_csv(path, sep="\t")`

2. **Run the Buckaroo dataflow** to compute display metadata:
   - Reuse existing `CustomizableDataFlow` pipeline (or a headless subset of it)
   - Produces: `df_display_args`, `df_data_dict` (stats), `df_meta` (total_rows, column info)
   - This gives the browser the same column configs, summary stats, and viewer config as Jupyter

3. **Store in session state** and push metadata to connected WebSocket clients.

### Handling `_handle_payload_args` outside the widget

The row-slicing logic in `BuckarooInfiniteWidget._handle_payload_args()` is ~30 lines and doesn't depend on the widget class. We can either:
- **Extract it** into a standalone function: `handle_payload_args(df, merged_sd, payload_args) → (json_msg, parquet_bytes)`
- **Or reuse it** by instantiating a headless `BuckarooInfiniteWidget` (it's just a Python object, doesn't need a browser)

Extracting is cleaner. The core logic is just:
```python
def handle_infinite_request(processed_df, merged_sd, payload_args):
    start, end = payload_args['start'], payload_args['end']
    sort = payload_args.get('sort')
    if sort:
        orig_col = merged_sd[sort]['orig_col_name']
        ascending = payload_args.get('sort_direction') == 'asc'
        sorted_df = processed_df.sort_values(by=[orig_col], ascending=ascending)
        slice_df = sorted_df[start:end]
    else:
        slice_df = processed_df[start:end]
    return to_parquet(slice_df), len(processed_df)
```

---

## Testing Strategy

### 1. Server HTTP tests (pytest + tornado.testing)

```python
class TestHealth(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_health(self):
        resp = self.fetch("/health")
        self.assertEqual(resp.code, 200)
        self.assertEqual(json.loads(resp.body), {"status": "ok"})

    def test_load(self):
        resp = self.fetch("/load", method="POST",
            body=json.dumps({"session": "test-1", "path": "/tmp/test.csv"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 200)
        body = json.loads(resp.body)
        self.assertIn("rows", body)
        self.assertIn("columns", body)

    def test_session_page(self):
        resp = self.fetch("/s/test-session")
        self.assertEqual(resp.code, 200)
        self.assertIn(b"standalone.js", resp.body)
```

No extra test dependencies — `tornado.testing` ships with Tornado.

### 2. WebSocket protocol tests (pytest + tornado.testing)

```python
@tornado.testing.gen_test
async def test_websocket_infinite_request(self):
    # Load a test file first
    self.fetch("/load", method="POST",
        body=json.dumps({"session": "ws-test", "path": fixture_path}),
        headers={"Content-Type": "application/json"})

    ws = await tornado.websocket.websocket_connect(
        f"ws://localhost:{self.get_http_port()}/ws/ws-test")

    # Should receive initial state
    msg = await ws.read_message()
    state = json.loads(msg)
    assert state["type"] == "initial_state"
    assert "df_display_args" in state

    # Send an infinite_request
    ws.write_message(json.dumps({
        "type": "infinite_request",
        "payload_args": {"start": 0, "end": 50, "sourceName": "default", "origEnd": 50}
    }))

    # Should get JSON text frame
    json_msg = json.loads(await ws.read_message())
    assert json_msg["type"] == "infinite_resp"
    assert json_msg["length"] > 0

    # Should get binary Parquet frame
    parquet_bytes = await ws.read_message()
    assert isinstance(parquet_bytes, bytes)
    assert len(parquet_bytes) > 0
```

### 3. Integration tests (Playwright)

The project already has Playwright set up. Add tests that:
1. Start `buckaroo-server` with a test fixture
2. Open the browser to `localhost:<port>/s/test`
3. POST `/load` with a test CSV/Parquet file
4. Verify the AG-Grid table renders with correct row count
5. Scroll and verify new rows load (WebSocket round-trip)
6. Sort a column and verify the data changes

These reuse the existing Playwright infrastructure in `packages/buckaroo-js-core/`.

### 4. Test fixtures

Create small test files in `tests/fixtures/`:
- `test_10rows.csv` — basic CSV, 10 rows, 5 columns
- `test_100k.parquet` — larger Parquet for scroll testing
- `test_types.csv` — mixed types (int, float, str, datetime) for serialization testing

---

## File Layout

```
buckaroo/
├── server/                          # New package
│   ├── __init__.py
│   ├── app.py                       # Tornado app, make_app(), routes
│   ├── handlers.py                  # HealthHandler, LoadHandler, SessionPageHandler
│   ├── websocket_handler.py         # DataStreamHandler (WebSocket)
│   ├── session.py                   # SessionState, session management
│   ├── data_loading.py              # File reading, dataflow pipeline (headless)
│   ├── focus.py                     # macOS AppleScript browser focus
│   └── __main__.py                  # CLI entry point: python -m buckaroo.server
├── serialization_utils.py           # Existing — reused as-is
├── dataflow/                        # Existing — reused for stats/config
└── static/
    ├── widget.js                    # Existing (Jupyter)
    ├── standalone.js                # New (browser-tab mode)
    └── compiled.css                 # Existing

packages/buckaroo-js-core/
├── src/
│   ├── WebSocketModel.ts            # New — WS adapter for model interface
│   ├── standalone.tsx               # New — browser-tab entry point
│   └── components/                  # Existing — unchanged
│       ├── BuckarooWidgetInfinite.tsx
│       ├── DFViewerParts/
│       │   ├── SmartRowCache.ts
│       │   └── gridUtils.ts
│       └── ...
```

---

## Sequence of Work

### Phase 1: Minimal server (HTTP + WebSocket, no real data)
1. Create `buckaroo/server/app.py` with Tornado routes
2. `/health` returns 200
3. `/load` accepts POST, stores session in memory
4. `/s/<id>` serves a placeholder HTML page
5. `/ws/<id>` accepts WebSocket, echoes messages back
6. Tests for all of the above
7. CLI entry: `python -m buckaroo.server --port 8888`

### Phase 2: Data loading + row serving
1. Implement `data_loading.py` — read CSV/Parquet/JSON into DataFrame
2. Run headless dataflow to compute display args and stats
3. WebSocket handler: receive `infinite_request`, call extracted `handle_infinite_request()`, send JSON + binary Parquet response
4. Tests: load a fixture CSV, request rows over WebSocket, verify Parquet bytes decode correctly

### Phase 3: JS standalone client
1. Create `WebSocketModel.ts` — adapter from WebSocket to model interface
2. Create `standalone.tsx` — entry point that connects, receives initial state, renders `DFViewerInfiniteDS`
3. Build with esbuild → `buckaroo/static/standalone.js`
4. Update `/s/<id>` to serve real HTML with the JS bundle
5. Manual test: start server, load a CSV, open browser, see the table

### Phase 4: Server push + browser focus
1. On `/load`, push `metadata` message to connected WebSocket clients for that session
2. Browser receives push, triggers re-render with new data
3. Implement macOS browser focus (`focus.py`)
4. Playwright integration test: full round-trip from `/load` to rendered table

### Phase 5: Polish
1. Auto-open browser on first `/load` for a session (`webbrowser.open()`)
2. Idle timeout — shut down server after N minutes with no WebSocket connections
3. Multiple files per session (replace current view)
4. Error handling (file not found, unsupported format, corrupt data)
5. Package as part of `buckaroo` or as separate `buckaroo-mcp`

---

## Open Questions

### 1. Should `buckaroo/server/` live in the existing `buckaroo` package or be a new top-level package?
- **In `buckaroo`**: Reuses serialization_utils, dataflow, etc. without cross-package imports. Tornado becomes a dependency of buckaroo.
- **Separate `buckaroo-server`**: Keeps Tornado out of the base buckaroo package. Needs to import from buckaroo as a dependency.
- Leaning toward **in `buckaroo`** with Tornado as an optional dependency (`pip install buckaroo[server]`).

### 2. Headless dataflow — how much of the widget pipeline do we reuse?
- The `CustomizableDataFlow` pipeline computes stats, display args, and column configs
- We want all of that for the standalone server (so the browser gets the same rich UI)
- Need to verify it works headless (no widget class, no traitlets sync)
- Might need a thin wrapper or to extract the pipeline into a function

### 3. Polars support
- The existing codebase has `lazy_infinite_polars_widget.py` with its own `_to_parquet()`
- The server should support both Pandas and Polars DataFrames
- File reading should auto-detect and use whichever is available
- Can defer Polars support to a later phase

### 4. Port selection
- Default well-known port (e.g., 8888) or auto-select a free port?
- If auto-select, the MCP server needs to discover which port the server is on
- Could write the port to a file: `~/.buckaroo/server.port`
- Or use a well-known port with fallback to next available
