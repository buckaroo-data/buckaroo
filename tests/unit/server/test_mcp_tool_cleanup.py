"""Tests that the MCP tool cleans up its server subprocess on exit.

These tests verify that:
1. ensure_server() stores the Popen handle in _server_proc
2. _cleanup_server() terminates the subprocess
3. Signal handlers are registered for SIGTERM/SIGINT
4. A pipe-based monitor kills the server even when the parent is SIGKILL'd

The ``mcp`` package is not installed in the dev environment, so we mock it
before importing buckaroo_mcp_tool.
"""

import os
import signal
import subprocess
import sys
import time
import types
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Mock away the ``mcp`` dependency so buckaroo_mcp_tool can be imported
# ---------------------------------------------------------------------------

def _ensure_mcp_mock():
    """Install a fake ``mcp`` package in sys.modules if not already present."""
    if "mcp" in sys.modules:
        return  # real package or already mocked

    mcp_mod = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_fastmcp = types.ModuleType("mcp.server.fastmcp")

    # FastMCP is used as a class: mcp = FastMCP("buckaroo-table", ...)
    fake_mcp_instance = MagicMock()
    # .tool() and .prompt() are used as decorators — return identity
    fake_mcp_instance.tool.return_value = lambda fn: fn
    fake_mcp_instance.prompt.return_value = lambda fn: fn
    mcp_fastmcp.FastMCP = MagicMock(return_value=fake_mcp_instance)

    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = mcp_server
    sys.modules["mcp.server.fastmcp"] = mcp_fastmcp


_ensure_mcp_mock()

# Now safe to import — remove from cache first so re-import picks up mocks
sys.modules.pop("buckaroo_mcp_tool", None)
import buckaroo_mcp_tool  # noqa: E402

# Repo root — needed so subprocess can find buckaroo_mcp_tool.py
REPO_ROOT = os.path.dirname(os.path.abspath(buckaroo_mcp_tool.__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spawn_sleep():
    """Spawn a long-running subprocess we can use as a stand-in for the server."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(600)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _is_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Tests — signal/atexit cleanup (graceful exit)
# ---------------------------------------------------------------------------

class TestServerProcessCleanup:
    """Verify that the MCP tool tracks and cleans up its server subprocess."""

    def test_module_has_server_proc_tracking(self):
        """_server_proc module-level variable must exist for tracking."""
        assert hasattr(buckaroo_mcp_tool, "_server_proc"), (
            "_server_proc attribute missing — server subprocess won't be tracked"
        )

    def test_module_has_cleanup_function(self):
        """_cleanup_server() must exist."""
        assert hasattr(buckaroo_mcp_tool, "_cleanup_server"), (
            "_cleanup_server function missing — no way to stop the server on exit"
        )
        assert callable(buckaroo_mcp_tool._cleanup_server)

    def test_ensure_server_stores_popen(self):
        """When ensure_server() spawns a new server, it must store the Popen
        handle in _server_proc so cleanup can find it later."""
        m = buckaroo_mcp_tool

        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_health = {"pid": 12345, "uptime_s": 0.1, "static_files": {}}

        with (
            patch.object(m, "_health_check", side_effect=[None, fake_health]),
            patch("subprocess.Popen", return_value=fake_proc),
            patch("builtins.open", MagicMock()),
            patch("time.sleep"),
        ):
            old_proc = m._server_proc
            try:
                result = m.ensure_server()
                assert result["server_status"] == "started"
                assert m._server_proc is fake_proc, (
                    "ensure_server() must store the Popen in _server_proc"
                )
            finally:
                m._server_proc = old_proc

    def test_cleanup_terminates_running_process(self):
        """_cleanup_server() must actually terminate a running subprocess."""
        m = buckaroo_mcp_tool

        proc = _spawn_sleep()
        try:
            assert _is_alive(proc.pid), "test setup: sleep process should be alive"

            old_proc = m._server_proc
            m._server_proc = proc
            m._cleanup_server()

            # Give OS a moment to reap
            proc.wait(timeout=5)
            assert not _is_alive(proc.pid), (
                "Server process still alive after _cleanup_server()"
            )
            assert m._server_proc is None, (
                "_server_proc should be set to None after cleanup"
            )
            m._server_proc = old_proc
        finally:
            # Safety net — always kill the sleep process no matter what
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_cleanup_noop_when_no_server(self):
        """_cleanup_server() should be a safe no-op when _server_proc is None."""
        m = buckaroo_mcp_tool

        old_proc = m._server_proc
        try:
            m._server_proc = None
            m._cleanup_server()  # should not raise
        finally:
            m._server_proc = old_proc

    def test_sigterm_handler_registered(self):
        """SIGTERM should have a custom handler (not SIG_DFL) for cleanup."""
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not signal.SIG_DFL, (
            "SIGTERM handler is SIG_DFL — server won't be cleaned up on mcp remove"
        )
        assert handler is not signal.SIG_IGN, (
            "SIGTERM handler is SIG_IGN — process won't exit on mcp remove"
        )


# ---------------------------------------------------------------------------
# Tests — pipe-based monitor (survives SIGKILL / os._exit)
# ---------------------------------------------------------------------------

class TestServerMonitor:
    """Verify that a pipe-based monitor kills the server when the MCP tool
    dies unexpectedly (SIGKILL, os._exit, etc.) — cases where atexit and
    signal handlers do NOT run."""

    def test_module_has_start_server_monitor(self):
        """_start_server_monitor() function must exist."""
        assert hasattr(buckaroo_mcp_tool, "_start_server_monitor"), (
            "_start_server_monitor missing — server will be orphaned on hard kill"
        )
        assert callable(buckaroo_mcp_tool._start_server_monitor)

    def test_server_killed_on_parent_death(self):
        """Server must die when MCP tool parent is SIGKILL'd.

        This simulates the worst case: Claude kills the MCP tool hard,
        bypassing all signal handlers and atexit callbacks. The only
        reliable mechanism is a pipe-based monitor process.
        """
        # Parent script imports buckaroo_mcp_tool (with mcp mocked),
        # spawns a "server" (sleep), starts the monitor, then blocks.
        parent_script = """\
import sys, os, types, subprocess, signal
from unittest.mock import MagicMock

# Mock mcp
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

import buckaroo_mcp_tool as m

# Start a "server" (sleep process)
server = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(600)"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
m._server_proc = server

# Start monitor if available (the fix adds this)
if hasattr(m, "_start_server_monitor"):
    m._start_server_monitor(server.pid)

# Report server PID
print(server.pid, flush=True)

# Block on stdin (simulating mcp.run())
sys.stdin.buffer.read()
"""

        parent = subprocess.Popen(
            [sys.executable, "-c", parent_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=REPO_ROOT,
        )

        server_pid = None
        try:
            line = parent.stdout.readline().decode().strip()
            server_pid = int(line)
            assert _is_alive(server_pid), "Server should be alive after start"

            # SIGKILL parent — no handlers run, no atexit, nothing.
            # Only the pipe-based monitor can save us.
            parent.kill()
            parent.wait(timeout=5)

            # Give the monitor time to detect pipe break and kill server
            for _ in range(20):
                if not _is_alive(server_pid):
                    break
                time.sleep(0.25)

            assert not _is_alive(server_pid), (
                f"Server (pid={server_pid}) survived parent SIGKILL — orphan!"
            )
        finally:
            if parent.poll() is None:
                parent.kill()
                try:
                    parent.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            if server_pid:
                try:
                    os.kill(server_pid, signal.SIGKILL)
                except OSError:
                    pass
