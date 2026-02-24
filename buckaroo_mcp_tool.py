"""Buckaroo MCP tool — lets Claude Code view tabular data files."""

import atexit
import json
import logging
import os
import signal
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

# Track server subprocess so we can kill it on exit
_server_proc: subprocess.Popen | None = None
_server_monitor: subprocess.Popen | None = None


def _start_server_monitor(server_pid: int):
    """Spawn a tiny watchdog process that kills the server if we die.

    The monitor blocks on a pipe from us.  When we exit — for ANY reason,
    including SIGKILL or os._exit() — the OS closes the pipe and the
    monitor wakes up and sends SIGTERM to the server.
    """
    global _server_monitor
    monitor_code = (
        "import os, sys, signal\n"
        f"server_pid = {server_pid}\n"
        "sys.stdin.buffer.read()\n"
        "try:\n"
        f"    os.kill(server_pid, signal.SIGTERM)\n"
        "except OSError:\n"
        "    pass\n"
    )
    _server_monitor = subprocess.Popen(
        [sys.executable, "-c", monitor_code],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.info("Started server monitor (pid=%d) watching server pid=%d",
             _server_monitor.pid, server_pid)


def _cleanup_server():
    """Terminate the data server and monitor if we started them."""
    global _server_proc, _server_monitor
    if _server_proc is not None:
        try:
            if _server_proc.poll() is None:  # still running
                log.info("Shutting down server (pid=%d)", _server_proc.pid)
                _server_proc.terminate()
                try:
                    _server_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    log.warning("Server didn't stop after SIGTERM, sending SIGKILL")
                    _server_proc.kill()
        except OSError as exc:
            log.debug("Cleanup error (harmless): %s", exc)
        _server_proc = None
    if _server_monitor is not None:
        try:
            _server_monitor.terminate()
            _server_monitor.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        _server_monitor = None


atexit.register(_cleanup_server)


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT by cleaning up the server, then re-raising."""
    log.info("Received signal %s — cleaning up", signal.Signals(signum).name)
    _cleanup_server()
    # Re-raise with default handler so the process actually exits
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


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


def _health_check() -> dict | None:
    """Returns the health response dict, or None if the server isn't reachable."""
    try:
        resp = urlopen(f"{SERVER_URL}/health", timeout=2)
        if resp.status == 200:
            data = json.loads(resp.read())
            log.debug("Health check OK: %s", data)
            return data
    except (URLError, OSError) as exc:
        log.debug("Health check failed: %s", exc)
    return None


def _get_diagnostics() -> dict | None:
    """Fetch /diagnostics from the running server."""
    try:
        resp = urlopen(f"{SERVER_URL}/diagnostics", timeout=5)
        if resp.status == 200:
            return json.loads(resp.read())
    except (URLError, OSError):
        pass
    return None


def _read_server_log_tail(n_lines: int = 30) -> str:
    """Read the last N lines of the server log for diagnostics."""
    server_log = os.path.join(LOG_DIR, "server.log")
    try:
        if os.path.isfile(server_log):
            with open(server_log) as f:
                lines = f.readlines()
            return "".join(lines[-n_lines:])
    except OSError:
        pass
    return "(server log not found)"


def _format_startup_failure() -> str:
    """Build a detailed error message when the server fails to start."""
    server_log = os.path.join(LOG_DIR, "server.log")
    mcp_log = LOG_FILE

    tail = _read_server_log_tail(20)

    return (
        f"Buckaroo data server failed to start.\n\n"
        f"## Diagnostic info\n"
        f"- Python: {sys.executable} ({sys.version.split()[0]})\n"
        f"- Server URL: {SERVER_URL}\n"
        f"- Log dir: {LOG_DIR}\n\n"
        f"## Server log (last 20 lines)\n```\n{tail}\n```\n\n"
        f"## What to check\n"
        f"1. Is port {SERVER_PORT} already in use? "
        f"(`lsof -i :{SERVER_PORT}`)\n"
        f"2. Check the full server log: `cat {server_log}`\n"
        f"3. Check the MCP tool log: `cat {mcp_log}`\n"
        f"4. Try starting the server manually: "
        f"`{sys.executable} -m buckaroo.server --no-browser --port {SERVER_PORT}`\n"
    )


def ensure_server() -> dict:
    """Start the Buckaroo data server if it isn't already running.

    Returns a dict with:
      - server_status: "reused" or "started"
      - server_pid: int
      - server_uptime_s: float
    """
    import buckaroo
    expected_version = getattr(buckaroo, "__version__", "unknown")

    health = _health_check()
    if health:
        running_version = health.get("version", "unknown")
        if running_version == expected_version:
            log.info("Server already running (v%s) — pid=%s uptime=%.0fs",
                     running_version, health.get("pid"), health.get("uptime_s", 0))
            return {
                "server_status": "reused",
                "server_pid": health.get("pid"),
                "server_uptime_s": health.get("uptime_s", 0),
            }
        else:
            old_pid = health.get("pid")
            log.info("Version mismatch: running=%s expected=%s — killing old server (pid=%s)",
                     running_version, expected_version, old_pid)
            if old_pid:
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(1)
                    # Verify it's gone; SIGKILL if not
                    if _health_check():
                        os.kill(old_pid, signal.SIGKILL)
                        time.sleep(0.5)
                except OSError as exc:
                    log.debug("Kill old server error (harmless): %s", exc)

    global _server_proc
    cmd = [sys.executable, "-m", "buckaroo.server"]

    server_log = os.path.join(LOG_DIR, "server.log")
    server_log_fh = open(server_log, "a")
    try:
        _server_proc = subprocess.Popen(cmd, stdout=server_log_fh, stderr=server_log_fh)
    finally:
        # Close the parent-side handle; the child inherits its own copy.
        server_log_fh.close()
    _start_server_monitor(_server_proc.pid)

    startup_timeout_s = float(os.environ.get("BUCKAROO_STARTUP_TIMEOUT", "5.0"))
    startup_retries = max(1, int(startup_timeout_s / 0.25))
    log.info(
        "Starting server: %s (startup_timeout=%.1fs retries=%d)",
        " ".join(cmd), startup_timeout_s, startup_retries,
    )

    for i in range(startup_retries):
        time.sleep(0.25)
        health = _health_check()
        if health:
            log.info("Server ready after %.1fs — pid=%s", (i + 1) * 0.25, health.get("pid"))
            # Check static files on first start
            static_files = health.get("static_files", {})
            missing = [
                name for name, info in static_files.items()
                if not info.get("exists") or info.get("size_bytes", 0) == 0
            ]
            if missing:
                log.warning("Static files missing or empty: %s — pages may be blank", missing)
            return {
                "server_status": "started",
                "server_pid": health.get("pid"),
                "server_uptime_s": health.get("uptime_s", 0),
            }

    log.error("Server failed to start within 5s — see %s", server_log)
    raise RuntimeError(_format_startup_failure())


def _view_impl(path: str) -> str:
    """Shared implementation for view_data / buckaroo_table."""
    path = os.path.abspath(path)
    log.info("view_data called — path=%s", path)

    try:
        server_info = ensure_server()
    except Exception:
        log.error("ensure_server failed:\n%s", traceback.format_exc())
        raise

    prompt = f"Viewing {os.path.basename(path)}"
    payload = json.dumps({"session": SESSION_ID, "path": path, "mode": "buckaroo", "prompt": prompt}).encode()
    log.debug("POST %s/load payload=%s", SERVER_URL, payload.decode())

    try:
        req = Request(
            f"{SERVER_URL}/load",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urlopen(req, timeout=30)
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
    browser_action = result.get("browser_action", "unknown")
    server_pid = result.get("server_pid", server_info.get("server_pid", "?"))

    summary = (
        f"Loaded **{os.path.basename(path)}** — "
        f"{rows:,} rows, {len(cols)} columns\n\n"
        f"Columns:\n{col_lines}\n\n"
        f"Interactive view: {url}\n"
        f"Server: pid={server_pid} ({server_info['server_status']}) | "
        f"Browser: {browser_action} | Session: {SESSION_ID}"
    )
    log.info("view_data success — %d rows, %d cols, browser=%s, server=%s(%s)",
             rows, len(cols), browser_action, server_pid, server_info["server_status"])
    return summary


@mcp.tool()
def view_data(path: str) -> str:
    """Load a tabular data file (CSV, TSV, Parquet, JSON) in Buckaroo for interactive viewing.

    Opens an interactive table UI in the browser and returns a text summary
    of the dataset (row count, column names and dtypes).
    """
    return _view_impl(path)


@mcp.tool()
def buckaroo_table(path: str) -> str:
    """Load a tabular data file (CSV, TSV, Parquet, JSON) in Buckaroo for interactive viewing.

    Opens an interactive table UI in the browser and returns a text summary
    of the dataset (row count, column names and dtypes).
    """
    return _view_impl(path)


@mcp.tool()
def buckaroo_diagnostics() -> str:
    """Run diagnostics on the Buckaroo data server.

    Returns server health, static file status, dependency info, and log
    locations to help debug issues like blank pages or server startup failures.
    """
    log.info("buckaroo_diagnostics called")

    # Try to reach the server
    health = _health_check()
    if not health:
        return (
            "Buckaroo server is NOT running.\n\n"
            + _format_startup_failure()
        )

    # Fetch full diagnostics
    diag = _get_diagnostics()
    if not diag:
        return (
            f"Server is running (pid={health.get('pid')}) but /diagnostics "
            f"endpoint unavailable. Server may be an older version.\n\n"
            f"Health: {json.dumps(health, indent=2)}"
        )

    # Format static file warnings
    static_files = diag.get("static_files", {})
    warnings = []
    for name, info in static_files.items():
        if not info.get("exists"):
            warnings.append(f"  MISSING: {name}")
        elif info.get("size_bytes", 0) == 0:
            warnings.append(f"  EMPTY: {name} (0 bytes — will cause blank page)")

    static_summary = "\n".join(
        f"  {name}: {'OK' if info.get('exists') and info.get('size_bytes', 0) > 0 else 'PROBLEM'} "
        f"({info.get('size_bytes', 0):,} bytes)"
        for name, info in static_files.items()
    )

    deps = diag.get("dependencies", {})
    dep_lines = "\n".join(
        f"  {name}: {'installed' if ok else 'MISSING'}"
        for name, ok in deps.items()
    )

    result = (
        f"## Buckaroo Server Diagnostics\n\n"
        f"Server: pid={diag.get('pid')} uptime={diag.get('uptime_s')}s\n"
        f"Python: {diag.get('python_version')} ({diag.get('python_executable')})\n"
        f"Buckaroo: {diag.get('buckaroo_version')}\n"
        f"Tornado: {diag.get('tornado_version')}\n"
        f"Platform: {diag.get('platform')}\n\n"
        f"### Static files\n{static_summary}\n\n"
        f"### Dependencies\n{dep_lines}\n\n"
        f"### Log files\n"
        f"  Log dir: {diag.get('log_dir')}\n"
        f"  Static path: {diag.get('static_path')}\n"
    )

    if warnings:
        result += "\n### WARNINGS\n" + "\n".join(warnings) + "\n"

    return result


def _start_parent_watcher():
    """Watch for parent process death (e.g. uvx killed by Claude).

    When this MCP tool is run via ``uvx``, there is an intermediate ``uv``
    process between Claude and us.  If Claude kills ``uv`` (SIGKILL), we
    become an orphan (reparented to PID 1 / launchd).  Detect that and
    exit so the pipe-based server monitor can fire.
    """
    import threading

    original_ppid = os.getppid()
    log.info("Parent watcher: original ppid=%d", original_ppid)

    def _watcher():
        while True:
            time.sleep(1)
            current_ppid = os.getppid()
            if current_ppid != original_ppid:
                log.info("Parent changed %d → %d — cleaning up", original_ppid, current_ppid)
                _cleanup_server()
                os._exit(0)

    t = threading.Thread(target=_watcher, daemon=True)
    t.start()


def main():
    _start_parent_watcher()
    mcp.run()


if __name__ == "__main__":
    main()
