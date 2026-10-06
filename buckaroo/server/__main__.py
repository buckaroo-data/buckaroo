import argparse
import atexit
import logging
import os
import signal
import sys
import threading

import tornado.httpserver
import tornado.ioloop
import tornado.netutil

from buckaroo.server.app import make_app
from buckaroo.server.security import remove_connection_file, resolve_token, write_connection_file

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_VALID_DATASET_KINDS = ("pandas", "lazy", "xorq")

# Port whose connection file this process owns, so every exit path (atexit,
# SIGTERM/SIGINT, the stdin watchdog's os._exit) can remove it. A stale token
# file left by a hard kill would otherwise linger in ~/.buckaroo/runtime.
_CONN_PORT: int | None = None


def _cleanup_connection_file():
    if _CONN_PORT is not None:
        remove_connection_file(_CONN_PORT)


def parse_dataset_spec(spec: str) -> dict:
    """Parse a single ``--dataset NAME=KIND:PATH`` spec into a
    ``{"label", "kind", "target"}`` dict.

    ``KIND`` is one of ``pandas`` / ``lazy`` / ``xorq``. For pandas and
    lazy, ``PATH`` is a data file (.csv/.parquet/...); for xorq it's a
    build dir produced by ``xorq build``. Raises ``ValueError`` for
    malformed specs and unknown kinds — argparse surfaces these as
    user-facing CLI errors via ``argparse.ArgumentTypeError`` (see
    ``_argparse_dataset`` below).

    See issue #811 — replaces the hard-coded demo paths previously baked
    into ``SESSION_HTML``."""
    if "=" not in spec:
        raise ValueError(
            f"--dataset spec missing '=': expected NAME=KIND:PATH, got {spec!r}")
    label, kind_and_target = spec.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError(f"--dataset spec has empty NAME: {spec!r}")
    if ":" not in kind_and_target:
        raise ValueError(
            f"--dataset spec missing ':' after KIND: expected NAME=KIND:PATH, got {spec!r}")
    kind, target = kind_and_target.split(":", 1)
    kind = kind.strip()
    target = target.strip()
    if kind not in _VALID_DATASET_KINDS:
        raise ValueError(
            f"--dataset spec has unknown kind {kind!r}: expected one of "
            f"{_VALID_DATASET_KINDS}, got {spec!r}")
    if not target:
        raise ValueError(f"--dataset spec has empty PATH: {spec!r}")
    return {"label": label, "kind": kind, "target": target}


def _argparse_dataset(spec: str) -> dict:
    """argparse adapter: convert ``ValueError`` from ``parse_dataset_spec``
    into ``argparse.ArgumentTypeError`` so argparse can format a nice
    ``usage:`` error and exit nonzero."""
    try:
        return parse_dataset_spec(spec)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def bind_and_make_app(port: int, open_browser: bool, datasets: list | None = None,
        token: str | None = None, allow_origins=()):
    """Bind the listening socket, then build the Application with the *bound*
    port stamped into ``settings``.

    ``--port=0`` asks the OS for an ephemeral port; ``bind_sockets`` returns
    the actual port it chose. ``LoadHandler._handle_browser_window`` reads
    ``settings['port']`` to build the ``http://localhost:<port>/s/<id>`` URL
    it asks the OS to focus, so the bound port — not the requested ``0`` —
    must end up in settings.

    ``token`` / ``allow_origins`` are passed straight through to ``make_app``.

    Returns ``(sockets, bound_port, app)``. Caller owns ``sockets``.
    """
    sockets = tornado.netutil.bind_sockets(port, address="127.0.0.1")
    bound_port = sockets[0].getsockname()[1]
    app = make_app(port=bound_port, open_browser=open_browser, datasets=datasets,
        token=token, allow_origins=allow_origins)
    return sockets, bound_port, app


def main():
    parser = argparse.ArgumentParser(description="Buckaroo data server")
    parser.add_argument("--port", type=int, default=8700, help="Port to listen on (0 = random)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on /load")
    parser.add_argument("--stdio-control", action="store_true",
        help="Exit when stdin closes. Used by parent supervisors (Tauri) to "
        "guarantee the sidecar dies when the parent does — closing stdin is "
        "more reliable than process-tree teardown across platforms.")
    parser.add_argument("--dataset", type=_argparse_dataset, action="append", default=[],
        metavar="NAME=KIND:PATH", dest="datasets",
        help="Register a dataset for the /s/<id> demo dropdown. Repeatable. "
        "KIND is one of pandas / lazy / xorq. PATH is a data file (pandas/lazy) "
        "or a build dir (xorq). Examples: "
        "--dataset boston-pandas=pandas:/data/boston.parquet "
        "--dataset boston-xorq=xorq:/builds/boston-xorq")
    parser.add_argument("--allow-origin", action="append", default=[], dest="allow_origins",
        metavar="ORIGIN",
        help="Extra browser origin allowed to open a WebSocket (beyond "
        "same-origin), for embedders — repeatable. E.g. "
        "--allow-origin tauri://localhost --allow-origin http://localhost:7860. "
        "'*' allows all origins. Also settable via BUCKAROO_ALLOW_ORIGIN "
        "(comma-separated).")
    args = parser.parse_args()

    # Line-buffer stdout so the BUCKAROO_PORT handshake reaches a parent supervisor
    # immediately when stdout is a pipe (Tauri/PyInstaller).
    sys.stdout.reconfigure(line_buffering=True)

    if args.stdio_control:
        # Background thread blocks on stdin; when the parent closes the pipe,
        # the read returns empty (EOF) and we exit. macOS/Linux only in v1;
        # Windows has different stdin-pipe semantics and is deferred with the
        # platform. On read exception, log to stderr before exiting so a
        # misconfigured supervisor (e.g. stdin not piped) is diagnosable
        # instead of silently terminating.
        def _stdin_watchdog():
            try:
                while sys.stdin.read(1):
                    pass
            except Exception as exc:
                print(f"buckaroo.server: --stdio-control watchdog read failed: {exc!r}; exiting",
                    file=sys.stderr)
            _cleanup_connection_file()
            os._exit(0)
        threading.Thread(target=_stdin_watchdog, daemon=True).start()

    # Configure server-side logging to file with timestamps. Logs go to file + stderr,
    # never stdout, so the handshake stays unambiguous.
    logging.basicConfig(filename=os.path.join(LOG_DIR, "server.log"), level=logging.DEBUG,
        format="%(asctime)s pid=%(process)d [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("buckaroo.server")
    log.info("Server starting — port=%d open_browser=%s pid=%d", args.port, not args.no_browser, os.getpid())

    # Default-on token (Jupyter model): BUCKAROO_TOKEN wins — an explicit
    # empty value disables auth; unset mints a fresh token. A parent
    # supervisor (the MCP tool, Tauri) sets BUCKAROO_TOKEN so it already
    # knows the token; a direct `buckaroo-server` launch gets a generated
    # one, surfaced below and in the connection file.
    token = resolve_token()
    allow_origins = list(args.allow_origins)
    env_origins = os.environ.get("BUCKAROO_ALLOW_ORIGIN", "")
    allow_origins += [o.strip() for o in env_origins.split(",") if o.strip()]

    sockets, bound_port, app = bind_and_make_app(port=args.port,
        open_browser=not args.no_browser, datasets=args.datasets,
        token=token, allow_origins=allow_origins)
    server = tornado.httpserver.HTTPServer(app)
    server.add_sockets(sockets)

    import buckaroo
    version = getattr(buckaroo, "__version__", "unknown")
    # Connection file: how a parent (the MCP tool) learns our pid + token
    # without an unauthenticated endpoint, and the pid it may safely kill.
    global _CONN_PORT
    _CONN_PORT = bound_port
    write_connection_file(bound_port, os.getpid(), token, version)
    atexit.register(_cleanup_connection_file)
    # atexit does not run on a signal, and the MCP tool stops the server with
    # SIGTERM — so remove the file (and its token) on the signal paths too,
    # then exit the way the default disposition would.
    def _on_signal(signum, _frame):
        _cleanup_connection_file()
        os._exit(0)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # Handshake line for parent-process supervisors (Tauri sidecar, etc.).
    # stdout was reconfigured to line_buffering above, so the newline flushes.
    print(f"BUCKAROO_PORT={bound_port}")
    if token:
        # To stderr (never stdout — that is the handshake channel) so a
        # direct launch can see how to reach the authenticated server.
        print(f"Buckaroo listening on http://127.0.0.1:{bound_port}/ "
            f"(token auth on) — e.g. http://127.0.0.1:{bound_port}/s/<id>?token={token}",
            file=sys.stderr)
        log.info("Server listening on http://127.0.0.1:%d (token auth enabled)", bound_port)
    else:
        print("WARNING: buckaroo server started with auth DISABLED "
            "(BUCKAROO_TOKEN=''). Any local process can read loaded data and "
            "load files.", file=sys.stderr)
        log.warning("Server listening on http://127.0.0.1:%d with auth DISABLED", bound_port)

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
