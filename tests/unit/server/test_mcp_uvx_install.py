"""Integration tests for the MCP install path.

These tests exercise the MCP tool entry point (``buckaroo-table``).  They can
run in two modes:

1. **Wheel mode** (CI default): Set ``BUCKAROO_MCP_CMD=buckaroo-table`` after
   pip-installing the built wheel.  The tests run against the just-built
   artifact — no network needed.

2. **uvx mode** (for manual testing against TestPyPI):  Leave
   ``BUCKAROO_MCP_CMD`` unset and the tests will use ``uvx`` to install from
   TestPyPI.

All tests are marked ``@pytest.mark.slow``.
Skip them with:  pytest -m "not slow"

Configuration via environment variables:
    BUCKAROO_MCP_CMD       If set, split into the command list (e.g. "buckaroo-table").
                           Overrides the uvx command entirely.
    BUCKAROO_MCP_PACKAGE   default: "buckaroo[mcp]"  (uvx mode only)
    BUCKAROO_INDEX_URL     default: "https://test.pypi.org/simple/"  (uvx mode only)
    BUCKAROO_EXTRA_INDEX   default: "https://pypi.org/simple/"  (uvx mode only)
"""

import csv
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import time
import urllib.request

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MCP_CMD_OVERRIDE = os.environ.get("BUCKAROO_MCP_CMD", "")

if _MCP_CMD_OVERRIDE:
    # Wheel mode: command is already installed (e.g. "buckaroo-table")
    MCP_CMD = _MCP_CMD_OVERRIDE.split()
    _can_run = shutil.which(MCP_CMD[0]) is not None
    skip_no_cmd = pytest.mark.skipif(
        not _can_run,
        reason=f"{MCP_CMD[0]!r} not on PATH (set by BUCKAROO_MCP_CMD)",
    )
else:
    # uvx mode: build the full uvx command
    UVX_PACKAGE = os.environ.get("BUCKAROO_MCP_PACKAGE", "buckaroo[mcp]")
    UVX_INDEX_URL = os.environ.get("BUCKAROO_INDEX_URL", "https://test.pypi.org/simple/")
    UVX_EXTRA_INDEX = os.environ.get("BUCKAROO_EXTRA_INDEX", "https://pypi.org/simple/")
    MCP_CMD = [
        "uvx",
        "--index-url", UVX_INDEX_URL,
        "--extra-index-url", UVX_EXTRA_INDEX,
        "--from", UVX_PACKAGE,
        "buckaroo-table",
    ]
    _can_run = shutil.which("uvx") is not None
    skip_no_cmd = pytest.mark.skipif(not _can_run, reason="uvx not on PATH")

slow = pytest.mark.slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_init_payload() -> bytes:
    """Build a newline-delimited JSON MCP initialize request.

    The MCP Python SDK stdio transport reads one JSON object per line.
    """
    msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test_mcp_uvx_install", "version": "0.1.0"},
        },
    })
    return (msg + "\n").encode()


def _find_jsonrpc_response(raw: bytes, target_id: int = 1) -> dict | None:
    """Find the JSON-RPC response with the given id in newline-delimited output.

    The server may emit notifications before the response, so we scan all lines.
    """
    text = raw.decode(errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("id") == target_id:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _send(proc, msg_dict: dict):
    """Send a newline-delimited JSON message to the MCP process."""
    line = json.dumps(msg_dict) + "\n"
    proc.stdin.write(line.encode())
    proc.stdin.flush()


def _recv(proc, target_id: int, timeout: float = 10) -> dict | None:
    """Read lines from the MCP process until we find a JSON-RPC response with the given id."""
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
        line = line.decode(errors="replace").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("id") == target_id:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _mcp_handshake(proc, request_id: int = 1):
    """Perform MCP initialize + initialized notification. Returns the init response."""
    _send(proc, {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test_mcp_uvx_install", "version": "0.1.0"},
        },
    })
    init_resp = _recv(proc, target_id=request_id)
    assert init_resp is not None, "No response to initialize"
    assert "result" in init_resp, f"initialize failed: {init_resp}"
    _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return init_resp


def _write_test_csv(path: str):
    """Write a small CSV for testing (matches test_server.py pattern)."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "age", "score"])
        for row in [
            ("Alice", 30, 88.5),
            ("Bob", 25, 92.3),
            ("Charlie", 35, 76.1),
            ("Diana", 28, 95.0),
            ("Eve", 32, 81.7),
        ]:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@slow
@skip_no_cmd
class TestMcpInstall:

    @pytest.mark.skipif(bool(_MCP_CMD_OVERRIDE), reason="not applicable in wheel mode")
    def test_uvx_resolves_package(self):
        """uvx can resolve and fetch buckaroo[mcp] without errors."""
        cmd = [
            "uvx",
            "--index-url", os.environ.get("BUCKAROO_INDEX_URL", "https://test.pypi.org/simple/"),
            "--extra-index-url", os.environ.get("BUCKAROO_EXTRA_INDEX", "https://pypi.org/simple/"),
            "--from", os.environ.get("BUCKAROO_MCP_PACKAGE", "buckaroo[mcp]"),
            "python", "-c", "import buckaroo_mcp_tool; print('ok')",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (
            f"uvx resolve failed:\nstdout: {r.stdout[:500]}\nstderr: {r.stderr[:500]}"
        )
        assert "ok" in r.stdout

    def test_uvx_no_stdout_pollution(self):
        """Running buckaroo-table via uvx must produce 0 bytes on stdout
        when stdin is immediately closed, OR only valid JSON-RPC lines.
        Any non-JSON stdout would corrupt the MCP protocol."""
        proc = subprocess.Popen(
            MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Close stdin immediately — server should exit cleanly
        proc.stdin.close()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

        if stdout:
            decoded = stdout.decode(errors="replace")
            # Every non-empty line must be valid JSON (newline-delimited JSON-RPC)
            for i, line in enumerate(decoded.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    pytest.fail(
                        f"uvx wrote non-JSON to stdout (line {i+1}), "
                        f"which would corrupt the MCP protocol:\n{line[:200]}"
                    )

    def test_uvx_mcp_handshake(self):
        """Pipe an MCP initialize message and verify we get a valid response
        with serverInfo.name == 'buckaroo-table'."""
        proc = subprocess.Popen(
            MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = _make_init_payload()
        try:
            stdout, stderr = proc.communicate(input=payload, timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.fail(
                f"MCP handshake timed out after 10s.\n"
                f"stdout ({len(stdout)}b): {stdout[:300]}\n"
                f"stderr ({len(stderr)}b): {stderr.decode(errors='replace')[:300]}"
            )

        assert len(stdout) > 0, (
            f"No response on stdout.\n"
            f"stderr: {stderr.decode(errors='replace')[:500]}"
        )

        resp = _find_jsonrpc_response(stdout)
        assert resp is not None, (
            f"Could not find JSON-RPC response (id=1) in stdout:\n"
            f"{stdout.decode(errors='replace')[:500]}"
        )
        assert "result" in resp, (
            f"JSON-RPC response has no 'result':\n{json.dumps(resp, indent=2)[:500]}"
        )
        server_info = resp["result"].get("serverInfo", {})
        assert server_info.get("name") == "buckaroo-table", (
            f"Expected serverInfo.name='buckaroo-table', got: {server_info}"
        )

    def test_uvx_startup_timing(self):
        """Time from process spawn to first JSON-RPC response must be < 15s."""
        proc = subprocess.Popen(
            MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = _make_init_payload()
        t0 = time.monotonic()
        try:
            stdout, _ = proc.communicate(input=payload, timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail("Startup took > 15s — too slow for MCP handshake")

        elapsed = time.monotonic() - t0
        assert len(stdout) > 0, "No response received"
        # Warn at 5s, fail at 15s
        if elapsed > 5:
            print(f"WARNING: startup took {elapsed:.1f}s (>5s threshold)")
        assert elapsed < 15, f"Startup took {elapsed:.1f}s — exceeds 15s limit"

    def test_mcp_protocol_via_uvx(self):
        """Full handshake: initialize -> list_tools -> verify view_data exists.

        Uses newline-delimited JSON (the MCP Python SDK stdio transport format).
        """
        proc = subprocess.Popen(
            MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Step 1: initialize + initialized notification
            _mcp_handshake(proc, request_id=1)

            # Step 2: list tools
            _send(proc, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            })
            tools_resp = _recv(proc, target_id=2)
            assert tools_resp is not None, "No response to tools/list"
            assert "result" in tools_resp, f"tools/list failed: {tools_resp}"

            tools = tools_resp["result"].get("tools", [])
            tool_names = [t["name"] for t in tools]
            assert "view_data" in tool_names, (
                f"view_data tool not found. Available tools: {tool_names}"
            )
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_view_data_call(self):
        """Call tools/call view_data and verify the response text AND that
        the Tornado server serves static assets correctly.

        This is the test that catches missing widget.js / standalone.js
        in the built wheel — it goes beyond tools/list to actually invoke
        the tool and then verify the HTTP server it starts.

        Uses the default port (8700) since the installed MCP tool starts
        the server without passing --port.
        """
        port = 8700

        proc = subprocess.Popen(
            MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        tmp_csv = None
        try:
            # Step 1: MCP handshake
            _mcp_handshake(proc, request_id=1)

            # Step 2: create a temp CSV
            tmp = tempfile.NamedTemporaryFile(
                suffix=".csv", delete=False, mode="w",
            )
            tmp_csv = tmp.name
            tmp.close()
            _write_test_csv(tmp_csv)

            # Step 3: tools/call view_data
            _send(proc, {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "view_data",
                    "arguments": {"path": tmp_csv},
                },
            })
            # view_data starts a Tornado server on first call — allow 30s
            call_resp = _recv(proc, target_id=3, timeout=30)
            assert call_resp is not None, (
                "No response to tools/call view_data (timed out after 30s)"
            )
            assert "result" in call_resp, (
                f"tools/call view_data failed: {call_resp}"
            )

            # The result.content is a list of content blocks
            content = call_resp["result"].get("content", [])
            text_parts = [
                c.get("text", "") for c in content if c.get("type") == "text"
            ]
            full_text = "\n".join(text_parts)

            # Verify the response mentions the file and row/column info
            basename = os.path.basename(tmp_csv)
            assert basename in full_text, (
                f"Expected filename '{basename}' in response text:\n{full_text[:500]}"
            )
            assert "5" in full_text, (
                f"Expected row count '5' in response text:\n{full_text[:500]}"
            )
            assert "3" in full_text, (
                f"Expected column count '3' in response text:\n{full_text[:500]}"
            )

            # Step 4: HTTP-fetch /health and verify static_files
            health_url = f"http://localhost:{port}/health"
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200, f"/health returned {resp.status}"
                health = json.loads(resp.read())

            static_files = health.get("static_files", {})
            critical = ["standalone.js", "standalone.css", "compiled.css", "widget.js"]
            # JS files must be non-empty; CSS files must exist but may be
            # empty in some builds (e.g. compiled.css can be 0 bytes).
            must_be_nonempty = {"standalone.js", "widget.js"}
            for fname in critical:
                info = static_files.get(fname)
                assert info is not None, (
                    f"static_files missing '{fname}': {static_files}"
                )
                assert info.get("exists") is True, (
                    f"Critical static file '{fname}' does not exist on disk: {info}"
                )
                if fname in must_be_nonempty:
                    assert info.get("size_bytes", 0) > 0, (
                        f"Critical static file '{fname}' is empty: {info}"
                    )

            # Step 5: HTTP-fetch an actual static asset to verify Tornado serves it
            js_url = f"http://localhost:{port}/static/standalone.js"
            req = urllib.request.Request(js_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200, (
                    f"GET /static/standalone.js returned {resp.status}"
                )
                body = resp.read()
                assert len(body) > 0, (
                    "standalone.js served but body is empty"
                )

        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if tmp_csv and os.path.exists(tmp_csv):
                os.unlink(tmp_csv)
