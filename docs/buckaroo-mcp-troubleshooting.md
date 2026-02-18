# Buckaroo MCP Troubleshooting

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
`uvx --reinstall buckaroo[mcp] buckaroo-table`.

### Server fails to start
- **Port in use**: Another process is using port 8700. Kill it with
  `lsof -ti:8700 | xargs kill` or set a different port with
  `BUCKAROO_PORT=8701`.
- **Missing tornado**: The `tornado` package isn't installed. This was fixed in
  v0.12.7 — upgrade with `uvx --reinstall buckaroo[mcp] buckaroo-table`.
- **Import error (polars)**: Fixed in v0.12.7.

### MCP tool connects but view_data fails
Check `~/.buckaroo/logs/mcp_tool.log` for the full traceback.
