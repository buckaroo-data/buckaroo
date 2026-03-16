"""Pre-run process cleanup — port of ci_pkill/kill_port from run-ci.sh."""
import os
import signal
import subprocess
import time
from pathlib import Path


def ci_pkill(pattern: str) -> None:
    """Kill processes matching pattern (excluding our own PID)."""
    my_pid = str(os.getpid())
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True,
        )
        pids = [p for p in result.stdout.strip().split("\n") if p and p != my_pid]
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (OSError, ValueError):
                pass
    except Exception:
        pass


def kill_port(port: int) -> None:
    """Kill process listening on a TCP port using /proc/net/tcp."""
    hex_port = f"{port:04X}"
    try:
        for tcp_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
            p = Path(tcp_file)
            if not p.exists():
                continue
            for line in p.read_text().splitlines()[1:]:
                parts = line.split()
                if len(parts) < 10:
                    continue
                local_addr = parts[1]
                if f":{hex_port}" in local_addr:
                    inode = parts[9]
                    _kill_by_inode(inode)
                    return
    except Exception:
        pass


def _kill_by_inode(inode: str) -> None:
    """Find and kill process owning a socket inode."""
    proc = Path("/proc")
    for pid_dir in proc.iterdir():
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        try:
            for fd in fd_dir.iterdir():
                try:
                    link = os.readlink(str(fd))
                    if link == f"socket:[{inode}]":
                        os.kill(int(pid_dir.name), signal.SIGKILL)
                        return
                except (OSError, ValueError):
                    continue
        except PermissionError:
            continue


def cleanup_processes() -> None:
    """Kill all stale CI processes from previous runs."""
    for pattern in [
        "chromium|chrome", "jupyter", "node.*playwright", "marimo",
        "jupyter-lab", "ipykernel", "node.*storybook", "npm exec serve",
        "npx.*serve", "esbuild", "buckaroo.server",
    ]:
        ci_pkill(pattern)

    for port in [8889, 8890, 8891, 8892, 8893, 8894, 8895, 8896, 8897,
                 2718, 6006, 8701, 8765]:
        kill_port(port)

    time.sleep(1)  # let processes die

    # Clean temp files
    import glob
    for pattern in [
        "/tmp/ci-jupyter-*", "/tmp/pw-*", "/tmp/.org.chromium.*",
        "/tmp/jupyter-port*.log", "/tmp/jlab-ws-*", "/tmp/tmp*.txt",
        "/tmp/playwright-artifacts-*", "/tmp/playwright_chromiumdev_profile-*",
    ]:
        for p in glob.glob(pattern):
            subprocess.run(["rm", "-rf", p], capture_output=True)

    # Clean Jupyter state
    for p in [
        os.path.expanduser("~/.jupyter/lab/workspaces"),
        "/repo/.jupyter/lab/workspaces",
    ]:
        subprocess.run(["rm", "-rf", p], capture_output=True)
    for pattern in [
        os.path.expanduser("~/.local/share/jupyter/runtime/kernel-*.json"),
        os.path.expanduser("~/.local/share/jupyter/runtime/jpserver-*.json"),
        os.path.expanduser("~/.local/share/jupyter/runtime/jpserver-*.html"),
    ]:
        for p in glob.glob(pattern):
            subprocess.run(["rm", "-f", p], capture_output=True)

    # Clean IPython/Jupyter caches
    subprocess.run(["rm", "-rf", os.path.expanduser("~/.ipython/profile_default/db")],
                   capture_output=True)
    subprocess.run(["rm", "-rf", os.path.expanduser("~/.local/share/jupyter/nbsignatures.db")],
                   capture_output=True)


def snapshot_container_state(label: str, outfile: str) -> None:
    """Capture container state for debugging."""
    parts = [
        f"=== Container snapshot: {label} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ===\n",
    ]
    for title, cmd in [
        ("Processes", ["ps", "aux", "--sort=-rss"]),
        ("/tmp listing", ["ls", "-la", "/tmp/"]),
        ("Memory", ["free", "-m"]),
    ]:
        parts.append(f"\n--- {title} ---\n")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            parts.append(result.stdout)
        except Exception:
            parts.append("(unavailable)\n")

    Path(outfile).parent.mkdir(parents=True, exist_ok=True)
    Path(outfile).write_text("".join(parts))
