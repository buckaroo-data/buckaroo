# Buckaroo MCP Server

## Install

### Option 1: From PyPI (recommended for most users)

Install the published package. Works from any directory:

```bash
claude mcp add buckaroo-table -- uvx --from "buckaroo[mcp]" buckaroo-table
```

### Option 2: From a local git checkout (for development)

If you're working on buckaroo itself and want the MCP tool to use your
local code, point `uv run` at the repo directory:

```bash
claude mcp add buckaroo-table -- uv run --directory /path/to/buckaroo python -m buckaroo_mcp_tool
```

Replace `/path/to/buckaroo` with the absolute path to your clone.

### Option 3: Global install (use from any directory)

Add `--scope user` so the MCP server is available in every Claude Code
session, not just the current project:

```bash
# From PyPI:
claude mcp add --scope user buckaroo-table -- uvx --from "buckaroo[mcp]" buckaroo-table

# Or from a local checkout:
claude mcp add --scope user buckaroo-table -- uv run --directory /path/to/buckaroo python -m buckaroo_mcp_tool
```

### Option 4: Project-level config (`.mcp.json`)

Add a `.mcp.json` file to the root of any repo so that every contributor
gets the MCP server automatically:

```json
{
  "mcpServers": {
    "buckaroo-table": {
      "command": "uvx",
      "args": ["--from", "buckaroo[mcp]", "buckaroo-table"]
    }
  }
}
```

## Upgrade

To force the latest version from PyPI, clear the uvx cache:

```bash
uv cache prune
```

The next time Claude Code starts a session, `uvx` will re-resolve and
fetch the latest `buckaroo[mcp]` from PyPI.

## MCP tools

The Buckaroo MCP server exposes:

- `view_data(path)` to open one data file.
- `compare_data(path1, path2, join_columns, how="outer")` to compare two files.

For multi-key joins, pass `join_columns` as a comma-separated string, for example:
`"account_id,order_id"`.

---

# Troubleshooting

If you're having trouble with the `buckaroo-table` MCP tool, paste the prompt
below into Claude Code. It will run diagnostics and give you output to share
with the maintainer.

---

## Diagnostic prompt

Copy everything between the `---` lines and paste it into Claude Code:

---

I'm having trouble with the buckaroo-table MCP tool. Please help me diagnose by doing the following steps in order:

1. **Run the diagnostics tool**: Use the `buckaroo_diagnostics` tool. This will check if the server is running, whether static files are present, and report dependency status.

2. **If the diagnostics tool isn't available** (older version), run these commands instead:
   - `curl -s http://localhost:8700/health | python3 -m json.tool` — check if the server is running
   - `curl -s http://localhost:8700/diagnostics | python3 -m json.tool` — get full diagnostics
   - `ls -la $(python3 -c "import buckaroo.server; import os; print(os.path.join(os.path.dirname(buckaroo.server.__file__), '..', 'static'))")` — check static files

3. **If the server isn't running**, try starting it manually:
   - `python3 -m buckaroo.server --no-browser --port 8700`
   - If that fails, share the error output.

4. **Check the logs**:
   - `cat ~/.buckaroo/logs/server.log | tail -50`
   - `cat ~/.buckaroo/logs/mcp_tool.log | tail -50`

5. **Check the installation**:
   - `python3 -c "import buckaroo; print(buckaroo.__version__)"` — version
   - `python3 -c "import tornado; print(tornado.version)"` — tornado present?
   - `pip show buckaroo | grep -i location` — install location

Please share ALL the output from the steps above so I can send it to the maintainer for diagnosis.

---

## Common issues

### Blank page (standalone.js not found)
The browser opens but shows a blank dark page. This means the static JS/CSS
files weren't included in the wheel. Fix: upgrade to the latest version with
`uv cache prune`, then restart Claude Code.

### Server fails to start
- **Port in use**: Another process is using port 8700. Kill it with
  `lsof -ti:8700 | xargs kill` or set a different port with
  `BUCKAROO_PORT=8701`.
- **Missing tornado**: The `tornado` package isn't installed. This was fixed in
  v0.12.7 — upgrade with `uv cache prune` and restart Claude Code.
- **Import error (polars)**: Fixed in v0.12.7.

### MCP tool connects but view_data fails
Check `~/.buckaroo/logs/mcp_tool.log` for the full traceback.

### compare_data opens but no histograms
You are likely on an older Buckaroo build without Buckaroo-mode compare sessions.
Upgrade (`uv cache prune`) and reconnect MCP. Compare sessions should include
`histogram` and `histogram_bins` summary rows.
