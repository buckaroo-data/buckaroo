# MCP Install Story: Packaging & Distribution

## Target User Experience

### Claude Code
```bash
claude mcp add buckaroo-table -- uvx buckaroo-table
```

### OpenAI Codex CLI
```toml
# .codex/config.toml
[mcp_servers.buckaroo-table]
command = "uvx"
args = ["buckaroo-table"]
```

### OpenAI Agents SDK
```python
from agents.mcp import MCPServerStdio
server = MCPServerStdio("uvx", ["buckaroo-table"])
```

### ChatGPT / OpenAI Responses API
Not possible today — requires remote HTTP server. Would need either a
hosted version or Streamable HTTP transport adapter. Separate effort.

---

## Current State

- `[project.scripts] buckaroo-table = "buckaroo.mcp_tool:main"` already defined
  in pyproject.toml — so `uvx buckaroo-table` should resolve to the right entry
  point once published
- `mcp` is in optional dependencies: `mcp = ["mcp"]`
- `tornado` is NOT declared as a dependency but is required for the server
- Package is on PyPI as `buckaroo` (version 0.12.5)

## Work Needed

| Task | Effort | Status |
|------|--------|--------|
| Add `tornado` to `mcp` optional deps in pyproject.toml | Small | TODO |
| Verify `uvx buckaroo-table` works end-to-end locally | Small | TODO |
| Publish updated package to PyPI | Small | TODO |
| Write install docs (README section + `claude mcp add` one-liner) | Small | TODO |
| Register on MCP registry (registry.modelcontextprotocol.io) | Medium | TODO |

---

## How Other Projects Handle It

### Packaging Patterns (from exploring 6 repos in ~/code/)

| Project | Language | Entry Point | Install |
|---------|----------|-------------|---------|
| Playwright MCP (27k stars) | Node | `bin: "cli.js"` | `npx @playwright/mcp@latest` |
| Chrome DevTools MCP (25k stars) | Node | `bin: "./build/src/index.js"` | `npx chrome-devtools-mcp@latest` |
| MCP Inspector (8.7k stars) | Node | `bin: "cli/build/cli.js"` | `npx @modelcontextprotocol/inspector` |
| BrowserTools MCP (7k stars) | Node | Two separate npx packages | User runs both manually |
| browser-use (805 stars) | Python | `[project.scripts]` in pyproject.toml | `uvx browser-use-mcp-server` |

**browser-use** is the closest analog to buckaroo (Python, pyproject.toml, uvx,
hatchling build system, similar architecture).

### Server Lifecycle Patterns

Three approaches observed:

1. **Lazy start on first tool call** — Chrome DevTools MCP, buckaroo (current)
   - Server/browser doesn't start until first tool invocation
   - Standard for tools that manage heavy resources

2. **Start everything on MCP server init** — MCP Inspector
   - Spawns web UI + proxy on startup, waits for readiness, opens browser
   - Good when the UI IS the product

3. **User starts components manually** — BrowserTools MCP
   - User runs middleware in separate terminal, MCP server discovers it via
     port probing + identity endpoint (/.identity returns signature)
   - Bad UX but good separation

**Decision: Keep lazy start.** It's the standard pattern and avoids wasting
resources when the tool isn't used.

### Browser Management

| Project | Approach |
|---------|----------|
| MCP Inspector | `open` npm package (like `webbrowser.open`) — no tab management |
| Playwright MCP | Launches browser via Playwright API, manages lifecycle directly |
| Chrome DevTools MCP | Reads `DevToolsActivePort` file to find running Chrome, or launches new |
| BrowserTools MCP | Chrome extension connects to middleware via WebSocket |
| browser-use | Launches Chromium via Playwright, no window reuse |

**Nobody else does AppleScript tab finding/focusing.** Most just call
`open(url)` or launch a fresh browser. Buckaroo's tab-reuse + reload
behavior is novel. Worth keeping as macOS-specific bonus UX.

---

## Future: ext-apps / MCP Apps (Inline UI)

The `ext-apps` spec (github.com/modelcontextprotocol/ext-apps, 1.5k stars)
lets MCP tools return HTML rendered in a sandboxed iframe by the host — no
local server needed.

**How it would work for buckaroo:**
- Tool returns `ui://buckaroo/viewer.html` resource
- Host (Claude Code, ChatGPT) renders the table inline
- Data flows via `structuredContent` + app-only tools for pagination
- No Tornado server, no browser management, no AppleScript

**Blockers:**
- Requires host adoption (Claude Code and ChatGPT would need to support ext-apps)
- Iframe sandbox limits WebSocket and binary streaming
- Large dataset performance unknown (chunked loading via RPC adds latency)

**Decision: Track as future path.** The local server + browser approach works
today across all MCP clients. ext-apps is the potential future but depends on
host support that doesn't exist yet.

---

## Resolved: Global Install, Not Per-Project

**Decision: One global system-wide install.** Not per-project.

```bash
claude mcp add --global buckaroo-table -- uvx buckaroo-table
```

**Why global:**
- Buckaroo is a general-purpose data viewer — useful across any project that touches dataframes, CSVs, parquet files. It's like `less` or a file viewer, not a project dependency.
- No project-specific config needed — it just renders dataframes. No schemas, no database connections, nothing project-specific.
- `uvx` already provides isolation — runs in its own ephemeral venv, no pollution of project dependencies, no version conflicts.
- Every comparable tool does global — Playwright MCP, Chrome DevTools MCP, browser-use are all installed once system-wide.
- Per-project kills adoption — if users have to add buckaroo to every project's `.mcp.json`, most won't bother.

**Per-project as an option (not the default):** Teams that want to standardize tools can use a checked-in `.mcp.json`. But docs lead with global.

---

## Upgrade Story

### The Problem

Two layers can go stale after a new PyPI release:

1. **`uvx` package cache** — `uvx buckaroo-table` reuses a cached venv. A new PyPI release doesn't automatically propagate.
2. **Running data server** — `ensure_server()` in `mcp_tool.py` checks `/health` and reuses the already-running server with no version check. Old server process stays alive on port 8700 indefinitely.

### User-Facing Upgrade Command

```bash
uvx --reinstall buckaroo-table
```

Use `--reinstall` not `--refresh`. `--reinstall` blows away the cached venv and rebuilds from scratch (implies `--refresh`). `--refresh` only re-checks PyPI metadata and may not rebuild. `--reinstall` removes ambiguity.

### Auto-Restart on Version Mismatch

After the user gets the new package, the stale running server needs to be replaced automatically. The MCP tool should handle this transparently:

1. **Add `version` to `/health` response** — currently only in `/diagnostics`. The MCP tool already hits `/health` on every `view_data` call, so don't require a second request.
2. **Add `POST /shutdown` endpoint** — graceful server stop. Returns `{"status": "shutting_down"}`, then calls `IOLoop.current().stop()` after a brief delay.
3. **Version check in `ensure_server()`** — compare `buckaroo.__version__` (from the MCP tool's venv) against the running server's reported version. If mismatch: POST `/shutdown`, wait for exit, start new server.

### Full Upgrade Flow (User Experience)

```
1. uvx --reinstall buckaroo-table        # pull latest from PyPI
2. (use Claude Code normally)             # MCP tool sees version mismatch,
                                          # auto-restarts stale server — invisible
```

Step 2 requires no user action. The MCP tool handles everything.

### Update Check: Notify User of New PyPI Releases

The MCP tool should check whether a newer version of buckaroo is available on PyPI and nudge the user to upgrade. This is separate from the auto-restart logic (which handles a version mismatch between MCP tool and running server). This handles the case where the user has an old version of everything and doesn't know there's a new release.

**How it works:**

1. **Check PyPI JSON API** — `GET https://pypi.org/pypi/buckaroo/json` returns `{"info": {"version": "X.Y.Z"}, ...}`. Compare against `buckaroo.__version__`.
2. **Don't check on every call** — adds latency. Check once per MCP tool process (i.e. once per Claude Code session). Cache the result in a module-level variable.
3. **Non-blocking** — run the PyPI check with a short timeout (2s). If PyPI is unreachable, skip silently. Never let an update check break `view_data`.
4. **Surface in tool result** — if a newer version exists, append a line to the `view_data` return string:
   ```
   Update available: buckaroo 0.13.0 → 0.14.0
   Run: uvx --reinstall buckaroo-table
   ```
   This way the LLM sees it and can relay it to the user. No popups, no blocking — just a note in the response.
5. **Optional: check frequency file** — to avoid checking PyPI on every Claude Code session, write the last-checked timestamp + latest version to `~/.buckaroo/update_check.json`. Only re-check if >24 hours since last check. This avoids unnecessary network calls across short-lived sessions.

**Sketch:**

```python
import buckaroo

_update_info: dict | None = None  # cached per-process

def check_for_update() -> str | None:
    """Returns an update message if a newer version exists, else None."""
    global _update_info
    if _update_info is not None:
        return _update_info.get("message")

    current = getattr(buckaroo, "__version__", "0.0.0")
    try:
        resp = urlopen("https://pypi.org/pypi/buckaroo/json", timeout=2)
        data = json.loads(resp.read())
        latest = data["info"]["version"]
    except Exception:
        _update_info = {}
        return None

    if latest != current:
        msg = (f"Update available: buckaroo {current} → {latest}\n"
               f"Run: uvx --reinstall buckaroo-table")
        _update_info = {"message": msg}
        return msg

    _update_info = {}
    return None
```

### Implementation Notes

- `/diagnostics` already returns `buckaroo_version` (handlers.py:77) — just need to add it to `/health` too
- MCP tool spawns the data server via `sys.executable` (same uvx venv), so they're always version-matched when started together
- The only gap is detecting and replacing a *previously started* server from an older venv

---

## Reference Repos (cloned to ~/code/)

```
~/code/
├── mcp-inspector/          # Two-port web UI + proxy (closest to buckaroo arch)
├── playwright-mcp/         # Gold standard npx packaging (27k stars)
├── mcp-ext-apps/           # Inline iframe UI spec (future path)
├── browser-tools-mcp/      # 3-component: extension + middleware + MCP
├── chrome-devtools-mcp/    # Chrome process detection via DevToolsActivePort
└── browser-use-mcp-server/ # Python/uvx, closest packaging analog
```
