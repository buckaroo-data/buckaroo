"""Integration tests for the Buckaroo MCP server process lifecycle.

These tests exercise real subprocess launches of ``python -m buckaroo.server``
and the ``ensure_server()`` function from ``buckaroo_mcp_tool``.

Tests 1, 3, 4, 5 run against the source tree (no wheel needed).
Test 2 (kill_stdio) requires the built wheel / ``BUCKAROO_MCP_CMD``.

All tests are marked ``@pytest.mark.slow`` and are Unix-only (signal-based
cleanup).  Skip with: ``pytest -m "not slow"``
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import types
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import urlopen

import pytest

# ---------------------------------------------------------------------------
# Markers / skips
# ---------------------------------------------------------------------------

slow = pytest.mark.slow

pytestmark = [
    slow,
    pytest.mark.skipif(sys.platform == "win32", reason="Unix signal-based tests"),
]

# ---------------------------------------------------------------------------
# Mock away ``mcp`` so buckaroo_mcp_tool can be imported without the package
# ---------------------------------------------------------------------------

def _ensure_mcp_mock():
    if "mcp" in sys.modules:
        return
    mcp_mod = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_fastmcp = types.ModuleType("mcp.server.fastmcp")
    fake = MagicMock()
    fake.tool.return_value = lambda fn: fn
    fake.prompt.return_value = lambda fn: fn
    mcp_fastmcp.FastMCP = MagicMock(return_value=fake)
    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = mcp_server
    sys.modules["mcp.server.fastmcp"] = mcp_fastmcp


_ensure_mcp_mock()
sys.modules.pop("buckaroo_mcp_tool", None)
import buckaroo_mcp_tool  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.abspath(buckaroo_mcp_tool.__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return an ephemeral port that is currently free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_death(pid: int, timeout: float = 5.0) -> bool:
    """Wait until a process is no longer alive. Returns True if it died."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return True
        time.sleep(0.25)
    return False


def _poll_health(port: int, timeout: float = 10.0) -> dict | None:
    """Poll /health until it responds or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urlopen(f"http://localhost:{port}/health", timeout=2)
            if resp.status == 200:
                return json.loads(resp.read())
        except (URLError, OSError, ValueError):
            pass
        time.sleep(0.25)
    return None


def _poll_health_gone(port: int, timeout: float = 10.0) -> bool:
    """Poll until /health stops responding. Returns True if it stopped."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://localhost:{port}/health", timeout=1)
        except (URLError, OSError):
            return True
        time.sleep(0.25)
    return False


def _start_server(port: int) -> subprocess.Popen:
    """Start ``python -m buckaroo.server`` on the given port.

    Captures stderr so failures can be diagnosed.
    """
    proc = subprocess.Popen(
        [sys.executable, "-m", "buckaroo.server", "--port", str(port), "--no-browser"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        cwd=REPO_ROOT,
    )
    return proc


def _kill_proc(proc: subprocess.Popen):
    """Best-effort kill and reap."""
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _kill_pid(pid: int):
    """Best-effort kill a process by PID."""
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Test 1: Server starts as subprocess and responds to health check
# ---------------------------------------------------------------------------

class TestServerSubprocessHealthCheck:
    """Spawn ``python -m buckaroo.server`` and verify /health responds."""

    def test_server_starts_and_responds(self):
        port = _free_port()
        proc = _start_server(port)
        try:
            health = _poll_health(port, timeout=15)
            if health is None:
                # Read stderr for diagnostics
                proc.terminate()
                try:
                    _, stderr = proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, stderr = proc.communicate()
                stderr_text = stderr.decode(errors="replace")[:1000] if stderr else "(empty)"
                pytest.fail(
                    f"Server did not respond to /health within 15s on port {port}\n"
                    f"exit code: {proc.returncode}\nstderr: {stderr_text}"
                )

            assert health["status"] == "ok"
            assert isinstance(health["pid"], int)
            assert isinstance(health["uptime_s"], (int, float))
            assert "version" in health

            # Terminate cleanly
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            assert proc.returncode is not None
        finally:
            _kill_proc(proc)


# ---------------------------------------------------------------------------
# Test 2: Killing MCP stdio process kills the tornado server
# ---------------------------------------------------------------------------

# This test needs the built wheel (buckaroo-table entry point).
_MCP_CMD_OVERRIDE = os.environ.get("BUCKAROO_MCP_CMD", "")
_has_mcp_cmd = bool(_MCP_CMD_OVERRIDE) and all(
    __import__("shutil").which(part) is not None
    for part in _MCP_CMD_OVERRIDE.split()[:1]
)


class TestKillStdioKillsTornado:
    """When the MCP stdio process is killed, the tornado server must die too."""

    @pytest.mark.skipif(not _has_mcp_cmd, reason="BUCKAROO_MCP_CMD not set or not on PATH")
    def test_kill_stdio_kills_tornado(self):
        """Start real MCP tool, trigger server via view_data, then SIGKILL
        the MCP process and confirm the tornado server stops."""
        import csv
        import selectors
        import tempfile

        mcp_cmd = _MCP_CMD_OVERRIDE.split()

        proc = subprocess.Popen(
            mcp_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        tmp_csv = None
        server_port = 8700  # default port used by MCP tool
        try:
            # MCP handshake
            def send(msg):
                proc.stdin.write((json.dumps(msg) + "\n").encode())
                proc.stdin.flush()

            def recv(target_id, timeout=10):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    sel = selectors.DefaultSelector()
                    sel.register(proc.stdout, selectors.EVENT_READ)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        sel.close()
                        break
                    events = sel.select(timeout=remaining)
                    sel.close()
                    if not events:
                        break
                    line = proc.stdout.readline()
                    if not line:
                        return None
                    try:
                        obj = json.loads(line.decode(errors="replace").strip())
                        if isinstance(obj, dict) and obj.get("id") == target_id:
                            return obj
                    except json.JSONDecodeError:
                        continue
                return None

            send({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test_integration", "version": "0.1.0"},
                },
            })
            init_resp = recv(1)
            assert init_resp is not None, "No response to initialize"
            assert "result" in init_resp, f"initialize failed: {init_resp}"
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})

            # Create temp CSV
            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
            tmp_csv = tmp.name
            tmp.close()
            with open(tmp_csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["a", "b"])
                w.writerow([1, 2])

            # Call view_data — this starts the tornado server
            send({
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "view_data", "arguments": {"path": tmp_csv}},
            })
            call_resp = recv(2, timeout=30)
            assert call_resp is not None, "No response to view_data"

            # Verify tornado is up
            health = _poll_health(server_port, timeout=5)
            assert health is not None, "Tornado server not responding after view_data"

            # SIGKILL the MCP stdio process
            proc.kill()
            proc.wait(timeout=5)

            # Tornado server should stop (monitor pipe fires)
            gone = _poll_health_gone(server_port, timeout=15)
            assert gone, (
                f"Tornado server on port {server_port} still responding "
                f"after MCP process was killed"
            )
        finally:
            _kill_proc(proc)
            if tmp_csv and os.path.exists(tmp_csv):
                os.unlink(tmp_csv)
            # Best-effort cleanup: kill any server left on the port
            try:
                resp = urlopen(f"http://localhost:{server_port}/health", timeout=1)
                health = json.loads(resp.read())
                pid = health.get("pid")
                if pid:
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Test 3: Port conflict — non-buckaroo process on port
# ---------------------------------------------------------------------------

class TestPortConflictNonBuckaroo:
    """When ensure_server() finds a non-buckaroo process on the port,
    it should raise RuntimeError (not hang or crash silently)."""

    def test_non_buckaroo_on_port_raises(self):
        port = _free_port()

        # Start a simple HTTP server that returns non-JSON on /health
        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"not-buckaroo")

            def log_message(self, format, *args):
                pass  # suppress logs

        httpd = HTTPServer(("127.0.0.1", port), _Handler)
        thread = Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        m = buckaroo_mcp_tool
        old_proc = m._server_proc
        old_monitor = getattr(m, "_server_monitor", None)
        spawned_proc = None
        try:
            with (
                patch.object(m, "SERVER_URL", f"http://localhost:{port}"),
                patch("time.sleep"),
            ):
                # _health_check() gets non-JSON from fake server → returns None
                # ensure_server() spawns a new server (default port) and polls
                # health against our fake URL → still non-JSON → None
                # After 20 retries → RuntimeError
                with pytest.raises(RuntimeError, match="failed to start"):
                    m.ensure_server()
                spawned_proc = m._server_proc
        finally:
            httpd.shutdown()
            # Clean up any process spawned by ensure_server
            if spawned_proc is not None:
                _kill_proc(spawned_proc)
            m._server_proc = old_proc
            if hasattr(m, "_server_monitor"):
                if m._server_monitor is not None and m._server_monitor is not old_monitor:
                    try:
                        m._server_monitor.terminate()
                        m._server_monitor.wait(timeout=2)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                m._server_monitor = old_monitor


# ---------------------------------------------------------------------------
# Test 4: Port conflict — stale buckaroo server with version mismatch
# ---------------------------------------------------------------------------

class TestVersionMismatchRestart:
    """When ensure_server() finds a running buckaroo server with a different
    version, it should kill the old server and start a new one."""

    def test_version_mismatch_kills_old_server(self):
        port = _free_port()
        old_server = _start_server(port)
        new_server_procs = []
        try:
            health = _poll_health(port, timeout=15)
            assert health is not None, "Old server did not start"
            old_pid = health["pid"]
            real_version = health["version"]

            m = buckaroo_mcp_tool
            saved_proc = m._server_proc
            saved_monitor = getattr(m, "_server_monitor", None)

            fake_version = real_version + ".fake"
            import buckaroo
            original_version = getattr(buckaroo, "__version__", "unknown")

            try:
                buckaroo.__version__ = fake_version

                # Redirect the new server Popen to use our port
                original_popen = subprocess.Popen

                def patched_popen(cmd, **kwargs):
                    if isinstance(cmd, list) and "-m" in cmd and "buckaroo.server" in cmd:
                        cmd = list(cmd) + ["--port", str(port), "--no-browser"]
                    p = original_popen(cmd, **kwargs)
                    new_server_procs.append(p)
                    return p

                with (
                    patch.object(m, "SERVER_URL", f"http://localhost:{port}"),
                    patch("subprocess.Popen", side_effect=patched_popen),
                ):
                    result = m.ensure_server()

                assert result["server_status"] == "started"

                # Reap the old server subprocess (it's a zombie until waited)
                try:
                    old_server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                assert _wait_for_death(old_pid, timeout=5), (
                    f"Old server (pid={old_pid}) still alive after version mismatch restart"
                )

                # New server should be responding
                new_health = _poll_health(port, timeout=5)
                assert new_health is not None, "New server not responding after restart"
            finally:
                buckaroo.__version__ = original_version
                m._server_proc = saved_proc
                if hasattr(m, "_server_monitor"):
                    if m._server_monitor is not None and m._server_monitor is not saved_monitor:
                        try:
                            m._server_monitor.terminate()
                            m._server_monitor.wait(timeout=2)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                    m._server_monitor = saved_monitor
        finally:
            _kill_proc(old_server)
            for p in new_server_procs:
                _kill_proc(p)
            # Final safety: kill anything on our port
            try:
                resp = urlopen(f"http://localhost:{port}/health", timeout=1)
                h = json.loads(resp.read())
                if h.get("pid"):
                    _kill_pid(h["pid"])
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Test 5: ensure_server() reuses running server with matching version
# ---------------------------------------------------------------------------

class TestReuseMatchingServer:
    """When a server is already running with the correct version,
    ensure_server() should reuse it without spawning a new process."""

    def test_reuse_matching_version(self):
        port = _free_port()
        server = _start_server(port)
        try:
            health = _poll_health(port, timeout=15)
            assert health is not None, "Server did not start"

            m = buckaroo_mcp_tool
            saved_proc = m._server_proc
            saved_monitor = getattr(m, "_server_monitor", None)

            try:
                with (
                    patch.object(m, "SERVER_URL", f"http://localhost:{port}"),
                    patch("subprocess.Popen") as mock_popen,
                ):
                    result = m.ensure_server()

                assert result["server_status"] == "reused"
                assert result["server_pid"] == health["pid"]
                mock_popen.assert_not_called()
            finally:
                m._server_proc = saved_proc
                if hasattr(m, "_server_monitor"):
                    m._server_monitor = saved_monitor
        finally:
            _kill_proc(server)
