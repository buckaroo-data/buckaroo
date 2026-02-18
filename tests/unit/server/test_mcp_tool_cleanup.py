"""Tests that the MCP tool cleans up its server subprocess on exit.

These tests verify that:
1. ensure_server() stores the Popen handle in _server_proc
2. _cleanup_server() terminates the subprocess
3. Signal handlers are registered for SIGTERM/SIGINT

The ``mcp`` package is not installed in the dev environment, so we mock it
before importing buckaroo_mcp_tool.
"""

import os
import signal
import subprocess
import sys
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
# Tests
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
