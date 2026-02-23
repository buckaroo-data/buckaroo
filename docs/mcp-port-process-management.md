# MCP Server: Port & Process Management

## Overview

When Claude Code calls `view_data`, the MCP tool spawns a **Tornado HTTP server** as a child process and communicates with it over localhost. Three cooperating mechanisms ensure the server starts reliably, stays alive during the session, and dies when the session ends.

```
Claude Code
  └─ uvx (intermediate)
       └─ MCP tool process  (buckaroo_mcp_tool)
            ├─ Tornado server  (python -m buckaroo.server)
            └─ Monitor process (watchdog — blocks on stdin pipe)
```

---

## 1. Port Selection

| Component | How port is determined | Default |
|---|---|---|
| MCP tool (`mcp_tool.py:30`) | `BUCKAROO_PORT` env var | `8700` |
| Server (`server/__main__.py:15`) | `--port` CLI arg | `8700` |

**Known limitation:** The MCP tool reads `BUCKAROO_PORT` to decide where to _look_ for the server (health checks, POST /load), but it spawns the server with `python -m buckaroo.server` **without passing `--port`**, so the server always binds to 8700. Setting `BUCKAROO_PORT` to anything other than 8700 will cause a mismatch — the MCP tool will poll the wrong port and report a startup failure.

---

## 2. Server Startup (`ensure_server`)

`ensure_server()` is called on every `view_data` invocation. It follows this sequence:

```
1. GET http://localhost:8700/health  (2s timeout)
   │
   ├─ Server responds, version matches  →  return "reused"
   │
   ├─ Server responds, version MISMATCH
   │     → SIGTERM old PID, wait 1s
   │     → if still alive: SIGKILL, wait 0.5s
   │     → fall through to start new server
   │
   └─ No response (server not running)
         → fall through to start new server

2. Start server subprocess
     cmd = [sys.executable, "-m", "buckaroo.server"]
     stdout/stderr → ~/.buckaroo/logs/server.log

3. Start monitor subprocess (see §4)

4. Poll health endpoint: 20 iterations × 0.25s = 5s max
     → On first 200 OK: check static files, return "started"
     → After 5s with no response: raise RuntimeError
```

The health endpoint (`/health`) returns:
```json
{
  "status": "ok",
  "version": "0.12.9",
  "pid": 12345,
  "uptime_s": 3.2,
  "static_files": {
    "standalone.js": {"exists": true, "size_bytes": 1843200},
    "standalone.css": {"exists": true, "size_bytes": 9700},
    "compiled.css":   {"exists": true, "size_bytes": 0},
    "widget.js":      {"exists": true, "size_bytes": 3400000}
  }
}
```

After a successful startup, `ensure_server` logs a warning if any static files are missing or empty (size 0). This is informational — it doesn't block the server from starting.

---

## 3. Cleanup: Three Layers of Defense

The server must die when the MCP session ends. Because Claude Code can exit in several ways (graceful shutdown, SIGTERM, SIGKILL to the uvx process), there are three independent cleanup mechanisms:

### Layer 1: `atexit` handler

Registered at module import time. Runs during normal Python shutdown.

```
_cleanup_server():
  if server still running:
    SIGTERM → wait 3s → SIGKILL if needed
  terminate monitor process
```

### Layer 2: Signal handler (SIGTERM / SIGINT)

Catches signals that Python can intercept. Calls `_cleanup_server()`, then re-raises with the default handler so the process actually exits.

### Layer 3: Monitor watchdog (pipe-based)

This is the safety net for SIGKILL, which Python cannot intercept.

```python
# Spawned as a child of the MCP process
monitor = subprocess.Popen(
    [python, "-c", "sys.stdin.buffer.read(); os.kill(server_pid, SIGTERM)"],
    stdin=PIPE,
)
```

The monitor blocks on `stdin.buffer.read()`. When the MCP process dies — for _any_ reason, including SIGKILL — the OS closes the pipe. The read unblocks, and the monitor sends SIGTERM to the server.

### Layer 3b: Parent watcher thread

A daemon thread polls `os.getppid()` every second. If the parent PID changes (meaning the uvx intermediary was killed and the MCP process was reparented to PID 1/launchd), it calls `_cleanup_server()` and exits via `os._exit(0)`. This triggers the pipe-based monitor as a secondary effect.

### Summary

| Scenario | What fires |
|---|---|
| Normal exit / Ctrl-C | atexit + signal handler |
| SIGTERM to MCP process | Signal handler → atexit |
| SIGKILL to MCP process | Monitor (pipe closes) |
| SIGKILL to uvx (parent) | Parent watcher → cleanup → `os._exit` → monitor |

---

## 4. Version Mismatch Handling

When `ensure_server` finds a running server with a different version than the installed package:

1. Send `SIGTERM` to the old server PID (from the health response)
2. Wait 1 second
3. Re-check health — if the old server is still responding, send `SIGKILL`
4. Wait 0.5 seconds
5. Start a fresh server subprocess

This handles the case where a user upgrades the package and the old server is still running from a previous session.

---

## 5. Request Flow (`view_data`)

Once the server is confirmed healthy:

```
MCP tool                          Tornado server
   │                                    │
   │  POST /load                        │
   │  {"session": "abc123",             │
   │   "path": "/tmp/data.csv",         │
   │   "mode": "buckaroo"}              │
   │ ──────────────────────────────────► │
   │                                    │  - Load file into pandas/polars
   │                                    │  - Store in session manager
   │                                    │  - Open/focus browser tab
   │  {"rows": 5, "columns": [...],     │
   │   "server_pid": 12345,             │
   │   "browser_action": "focused"}     │
   │ ◄────────────────────────────────── │
   │                                    │
   │  Format summary text               │
   │  Return to Claude via MCP          │
```

The session ID is a random 12-char hex string generated once per MCP process lifetime. The browser accesses the interactive view at `http://localhost:8700/s/{session_id}`, which serves an HTML page loading `standalone.js` from `/static/`.

---

## 6. Static File Verification

The `/health` endpoint reports existence and byte-size of four critical files:

| File | Purpose | Must be non-empty |
|---|---|---|
| `standalone.js` | Main app bundle for browser view | Yes |
| `standalone.css` | Styles for standalone view | No (can be inlined) |
| `compiled.css` | Additional compiled styles | No (can be 0 bytes) |
| `widget.js` | Jupyter widget bundle | Yes |

The new `test_view_data_call` integration test verifies these files through the full MCP path: it calls `tools/call view_data`, then HTTP-fetches `/health` and `/static/standalone.js` to confirm the server is actually serving assets. This test caught that `widget.js` was 0 bytes in a recent TestPyPI wheel.
