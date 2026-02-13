"""Buckaroo MCP tool — lets Claude Code view tabular data files."""

import json
import logging
import os
import subprocess
import sys
import time
import traceback
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "mcp_tool.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("buckaroo.mcp_tool")

SERVER_PORT = int(os.environ.get("BUCKAROO_PORT", "8700"))
SERVER_URL = f"http://localhost:{SERVER_PORT}"
SESSION_ID = uuid.uuid4().hex[:12]

log.info("MCP tool starting — server=%s session=%s", SERVER_URL, SESSION_ID)

mcp = FastMCP(
    "buckaroo-table",
    instructions=(
        "When the user mentions or asks about a CSV, TSV, Parquet, or JSON data file, "
        "always use the view_data tool to display it interactively in Buckaroo. "
        "Prefer view_data over reading file contents directly."
    ),
)


@mcp.prompt()
def view(path: str) -> str:
    """Open a data file in the Buckaroo interactive table viewer."""
    return f"Use the view_data tool to load and display the file at {path}"


def _health_ok() -> bool:
    try:
        resp = urlopen(f"{SERVER_URL}/health", timeout=2)
        ok = resp.status == 200
        log.debug("Health check: status=%d ok=%s", resp.status, ok)
        return ok
    except (URLError, OSError) as exc:
        log.debug("Health check failed: %s", exc)
        return False


def ensure_server() -> None:
    """Start the Buckaroo data server if it isn't already running."""
    if _health_ok():
        log.info("Server already running")
        return

    cmd = [sys.executable, "-m", "buckaroo.server", "--no-browser"]
    log.info("Starting server: %s", " ".join(cmd))

    server_log = os.path.join(LOG_DIR, "server.log")
    server_log_fh = open(server_log, "a")
    subprocess.Popen(cmd, stdout=server_log_fh, stderr=server_log_fh)

    for i in range(20):
        time.sleep(0.25)
        if _health_ok():
            log.info("Server ready after %.1fs", (i + 1) * 0.25)
            return

    log.error("Server failed to start within 5s — see %s", server_log)
    raise RuntimeError(f"Failed to start Buckaroo data server — see {server_log}")


@mcp.tool()
def view_data(path: str) -> str:
    """Load a tabular data file (CSV, TSV, Parquet, JSON) in Buckaroo for interactive viewing.

    Opens an interactive table UI in the browser and returns a text summary
    of the dataset (row count, column names and dtypes).
    """
    path = os.path.abspath(path)
    log.info("view_data called — path=%s", path)

    try:
        ensure_server()
    except Exception:
        log.error("ensure_server failed:\n%s", traceback.format_exc())
        raise

    payload = json.dumps({"session": SESSION_ID, "path": path, "mode": "buckaroo"}).encode()
    log.debug("POST %s/load payload=%s", SERVER_URL, payload.decode())

    try:
        req = Request(
            f"{SERVER_URL}/load",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=10)
        body = resp.read()
        log.debug("Response status=%d body=%s", resp.status, body[:500])
    except Exception as exc:
        # Try to read the response body for HTTP errors
        err_body = ""
        if hasattr(exc, "read"):
            try:
                err_body = exc.read().decode(errors="replace")
            except Exception:
                pass
        log.error("HTTP request to /load failed: %s body=%s\n%s", exc, err_body, traceback.format_exc())
        raise

    result = json.loads(body)

    rows = result["rows"]
    cols = result["columns"]
    col_lines = "\n".join(f"  - {c['name']} ({c['dtype']})" for c in cols)

    url = f"{SERVER_URL}/s/{SESSION_ID}"
    summary = (
        f"Loaded **{os.path.basename(path)}** — "
        f"{rows:,} rows, {len(cols)} columns\n\n"
        f"Columns:\n{col_lines}\n\n"
        f"Interactive view: {url}"
    )
    log.info("view_data success — %d rows, %d cols", rows, len(cols))
    return summary


def main():
    mcp.run()


if __name__ == "__main__":
    main()
