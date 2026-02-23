#!/usr/bin/env python3
"""Diagnostic script for MCP server startup issues.

Run standalone:  python tests/unit/server/diagnose_mcp_startup.py

Collects environment, timing, and protocol info to compare across machines.
Share the output in https://github.com/buckaroo-data/buckaroo/issues/552
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import time


def _section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def _run(cmd: list[str], timeout: float = 15, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            **kwargs,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, -1, "", f"timed out after {timeout}s")


def diagnose_environment():
    _section("Environment")
    print(f"Python:       {sys.version}")
    print(f"Executable:   {sys.executable}")
    print(f"Platform:     {platform.platform()}")
    print(f"Architecture: {platform.machine()}")
    print(f"CWD:          {os.getcwd()}")

    # Package versions
    for pkg in ("mcp", "buckaroo"):
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "installed (no __version__)")
            print(f"{pkg:14s}{ver}")
        except ImportError:
            print(f"{pkg:14s}NOT INSTALLED")
        except Exception as exc:
            # buckaroo import can fail in dev checkout (missing widget.js)
            print(f"{pkg:14s}import error: {exc}")

    # uvx version
    uvx = shutil.which("uvx")
    if uvx:
        r = _run(["uvx", "--version"])
        print(f"uvx:          {r.stdout.strip() or r.stderr.strip()} ({uvx})")
    else:
        print("uvx:          NOT FOUND on PATH")


def diagnose_uvx_stdout_pollution():
    """Check if uvx writes anything to stdout before handing off to Python."""
    _section("uvx stdout pollution check")

    uvx = shutil.which("uvx")
    if not uvx:
        print("SKIP — uvx not on PATH")
        return

    # Run uvx with /dev/null as stdin and a script that exits immediately
    # Any stdout from uvx itself (before Python runs) would corrupt JSON-RPC
    r = _run(
        ["uvx", "--from", "buckaroo[mcp]", "python", "-c", ""],
        timeout=30,
    )
    if r.returncode == 127:
        print(f"SKIP — {r.stderr.strip()}")
        return

    stdout_bytes = len(r.stdout.encode())
    print(f"stdout bytes: {stdout_bytes}")
    print(f"stderr bytes: {len(r.stderr.encode())}")
    if stdout_bytes > 0:
        print(f"WARNING: uvx wrote {stdout_bytes} bytes to stdout!")
        print(f"  Content: {r.stdout[:200]!r}")
    else:
        print("OK — no stdout pollution from uvx")

    if r.stderr:
        print(f"stderr preview: {r.stderr[:300]}")


def diagnose_uvx_startup_timing():
    """Measure cold and warm startup times for uvx."""
    _section("uvx startup timing")

    uvx = shutil.which("uvx")
    if not uvx:
        print("SKIP — uvx not on PATH")
        return

    for label in ("cold", "warm"):
        t0 = time.monotonic()
        r = _run(
            ["uvx", "--from", "buckaroo[mcp]", "python", "-c", "print('ok')"],
            timeout=60,
        )
        elapsed = time.monotonic() - t0
        ok = r.stdout.strip() == "ok"
        print(f"{label:5s} start: {elapsed:.2f}s  (exit={r.returncode}, ok={ok})")
        if not ok and r.stderr:
            print(f"  stderr: {r.stderr[:200]}")


def diagnose_mcp_handshake():
    """Send an MCP initialize message via stdin and check for a response."""
    _section("MCP JSON-RPC handshake")

    uvx = shutil.which("uvx")
    if not uvx:
        print("SKIP — uvx not on PATH")
        return

    init_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "diagnose_mcp_startup", "version": "0.1.0"},
        },
    })
    # MCP stdio transport uses newline-delimited JSON (one JSON object per line)
    payload = init_msg + "\n"

    cmd = ["uvx", "--from", "buckaroo[mcp]", "buckaroo-table"]
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(input=payload.encode(), timeout=10)
        elapsed = time.monotonic() - t0
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        elapsed = time.monotonic() - t0
        print(f"TIMEOUT after {elapsed:.2f}s — server did not respond")
        if stderr:
            print(f"stderr: {stderr.decode(errors='replace')[:500]}")
        return
    except FileNotFoundError:
        print("SKIP — uvx not found")
        return

    print(f"Time to response: {elapsed:.2f}s")
    print(f"Exit code: {proc.returncode}")
    print(f"stdout bytes: {len(stdout)}")
    print(f"stderr bytes: {len(stderr)}")

    if stdout:
        decoded = stdout.decode(errors="replace")
        print(f"stdout preview: {decoded[:500]}")
        # Try to parse JSON-RPC response
        if "serverInfo" in decoded:
            print("OK — got serverInfo in response")
        elif "jsonrpc" in decoded:
            print("PARTIAL — got JSON-RPC but no serverInfo")
        else:
            print("WARNING — stdout doesn't look like JSON-RPC")
    else:
        print("FAIL — no stdout at all")

    if stderr:
        print(f"stderr preview: {stderr.decode(errors='replace')[:500]}")


def diagnose_log_file():
    """Show the tail of the MCP tool log."""
    _section("MCP tool log (last 30 lines)")

    log_file = os.path.expanduser("~/.buckaroo/logs/mcp_tool.log")
    if os.path.isfile(log_file):
        print(f"File: {log_file} ({os.path.getsize(log_file)} bytes)")
        with open(log_file) as f:
            lines = f.readlines()
        for line in lines[-30:]:
            print(f"  {line.rstrip()}")
    else:
        print(f"NOT FOUND: {log_file}")


def diagnose_port():
    """Check if anything is listening on port 8700."""
    _section("Port 8700 status")

    port = int(os.environ.get("BUCKAROO_PORT", "8700"))
    r = _run(["lsof", "-i", f":{port}", "-P", "-n"])
    if r.stdout.strip():
        print(f"Something is listening on port {port}:")
        print(r.stdout)
    else:
        print(f"Nothing listening on port {port}")


def main():
    print("Buckaroo MCP Startup Diagnostics")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    diagnose_environment()
    diagnose_uvx_stdout_pollution()
    diagnose_uvx_startup_timing()
    diagnose_mcp_handshake()
    diagnose_log_file()
    diagnose_port()

    _section("Done")
    print("Copy the output above into GitHub issue #552 for comparison.")


if __name__ == "__main__":
    main()
