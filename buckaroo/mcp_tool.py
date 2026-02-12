"""Buckaroo MCP tool — lets Claude Code view tabular data files."""

import json
import os
import subprocess
import sys
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

SERVER_PORT = int(os.environ.get("BUCKAROO_PORT", "8700"))
SERVER_URL = f"http://localhost:{SERVER_PORT}"
SESSION_ID = uuid.uuid4().hex[:12]

mcp = FastMCP("buckaroo-table")


def _health_ok() -> bool:
    try:
        resp = urlopen(f"{SERVER_URL}/health", timeout=2)
        return resp.status == 200
    except (URLError, OSError):
        return False


def ensure_server() -> None:
    """Start the Buckaroo data server if it isn't already running."""
    if _health_ok():
        return

    subprocess.Popen(
        [sys.executable, "-m", "buckaroo.server", "--no-browser"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(20):
        time.sleep(0.25)
        if _health_ok():
            return

    raise RuntimeError("Failed to start Buckaroo data server")


@mcp.tool()
def view_data(path: str) -> str:
    """Load a tabular data file (CSV, TSV, Parquet, JSON) in Buckaroo for interactive viewing.

    Opens an interactive table UI in the browser and returns a text summary
    of the dataset (row count, column names and dtypes).
    """
    path = os.path.abspath(path)
    ensure_server()

    payload = json.dumps({"session": SESSION_ID, "path": path}).encode()
    req = Request(
        f"{SERVER_URL}/load",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    resp = urlopen(req, timeout=10)
    result = json.loads(resp.read())

    rows = result["rows"]
    cols = result["columns"]
    col_lines = "\n".join(f"  - {c['name']} ({c['dtype']})" for c in cols)

    url = f"{SERVER_URL}/s/{SESSION_ID}"
    return (
        f"Loaded **{os.path.basename(path)}** — "
        f"{rows:,} rows, {len(cols)} columns\n\n"
        f"Columns:\n{col_lines}\n\n"
        f"Interactive view: {url}"
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
