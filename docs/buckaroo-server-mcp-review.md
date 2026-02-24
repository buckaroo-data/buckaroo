# Buckaroo MCP + Server Review

## Scope reviewed

- `buckaroo_mcp_tool.py`
- `buckaroo/server/__main__.py`
- `buckaroo/server/app.py`
- `buckaroo/server/handlers.py`
- `buckaroo/server/websocket_handler.py`
- `buckaroo/server/session.py`

## What looks good

1. **Operational robustness in the MCP launcher**
   - It includes health checks, version mismatch handling, startup diagnostics, and cleanup handlers for normal exits and many signal cases.
   - The extra watchdog process and parent watcher are thoughtful process-lifecycle safeguards.

2. **Good diagnostics surface on the HTTP server**
   - `/health` and `/diagnostics` include versioning, uptime, static asset checks, and dependency checks.
   - This is practical for debugging blank-page and startup issues.

3. **Reasonable session abstraction**
   - `SessionState` and `SessionManager` keep server/session concerns centralized.
   - The same path supports multiple modes (`viewer`, `buckaroo`, `lazy`) without separate APIs.

4. **Client state fanout behavior is clear**
   - Existing websocket clients get state updates when a new file is loaded.
   - New websocket clients receive current state on connect.

## Improvements worth prioritizing

### P0/P1 reliability and correctness

1. **Close the server log file handle opened in `ensure_server`**
   - `server_log_fh` is opened and passed to `subprocess.Popen`, but the handle is never closed in the parent process.
   - This can leak file descriptors across repeated starts.

2. **Add locking around `SessionManager.sessions`**
   - Tornado is generally single-threaded on the IOLoop, but session mutation and websocket fanout can still benefit from explicit safety if future threading/background work is introduced.
   - A simple `threading.Lock` or lock-free constrained access policy should be documented and enforced.

3. **Guard against unbounded session growth**
   - `SessionManager` has no eviction/TTL for dead sessions.
   - Long-running server usage may accumulate stale session objects and metadata in memory.

4. **Return structured error schema consistently**
   - Some paths return plain stack traces in JSON (`traceback.format_exc()`), which is useful for dev but noisy and potentially risky for broad exposure.
   - Consider a stable envelope: `{"error_code", "message", "details", "request_id"}` with stack traces gated behind debug mode.

### P1 performance and maintainability

5. **Keep full-state messaging, but reduce unnecessary rebroadcasts**
   - `_handle_buckaroo_state_change` currently re-emits a full `initial_state` each change, which matches Buckaroo's current message model.
   - Instead of patch/delta protocols, only rebroadcast when the effective server-side state actually changed, and skip no-op updates.

6. **Consolidate duplicated state assembly logic**
   - Similar state payload assembly appears in multiple places (`LoadHandler._push_state_to_clients`, `DataStreamHandler.open`, `_handle_buckaroo_state_change`).
   - A shared helper would reduce drift and simplify tests.

7. **Improve startup timeout configurability**
   - MCP startup waits for ~5 seconds fixed (`20 * 0.25`).
   - Expose timeout/retry settings via env vars for slower environments.

8. **Add request/response correlation IDs in logs**
   - A request ID carried from MCP -> `/load` -> websocket messages would simplify cross-component debugging.

### P2 security and hardening

9. **Review broad websocket origin policy (`check_origin` always true)**
   - It is acceptable for local dev tools, but should be explicitly documented and optionally configurable/restricted.

10. **Validate file path policy in `/load`**
   - The server loads whatever filesystem path is provided.
   - If this remains local-only by design, document trust assumptions. Otherwise add allowlists/working-directory constraints.

## Testing improvements

1. Add tests for session lifecycle (creation, reuse, eviction when implemented).
2. Add tests that assert log-handle cleanup and no descriptor leaks during repeated start/stop.
3. Add websocket contract tests that verify no-op Buckaroo state changes do not trigger redundant full-state broadcasts.
4. Add tests for configurable startup timeout behavior and degraded startup diagnostics.

## Suggested implementation order

1. Fix file-handle cleanup and add regression tests.
2. Add session TTL/eviction and metrics (active sessions count).
3. Introduce shared state message builder to remove duplication.
4. Add optional strict origin/path policies behind config flags.
