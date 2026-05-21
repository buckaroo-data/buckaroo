import argparse
import logging
import os
import sys
import threading

import tornado.httpserver
import tornado.ioloop
import tornado.netutil

from buckaroo.server.app import make_app

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_VALID_DATASET_KINDS = ("pandas", "lazy", "xorq")


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


def bind_and_make_app(port: int, open_browser: bool, datasets: list | None = None):
    """Bind the listening socket, then build the Application with the *bound*
    port stamped into ``settings``.

    ``--port=0`` asks the OS for an ephemeral port; ``bind_sockets`` returns
    the actual port it chose. ``LoadHandler._handle_browser_window`` reads
    ``settings['port']`` to build the ``http://localhost:<port>/s/<id>`` URL
    it asks the OS to focus, so the bound port — not the requested ``0`` —
    must end up in settings.

    Returns ``(sockets, bound_port, app)``. Caller owns ``sockets``.
    """
    sockets = tornado.netutil.bind_sockets(port, address="127.0.0.1")
    bound_port = sockets[0].getsockname()[1]
    app = make_app(port=bound_port, open_browser=open_browser, datasets=datasets)
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
            os._exit(0)
        threading.Thread(target=_stdin_watchdog, daemon=True).start()

    # Configure server-side logging to file with timestamps. Logs go to file + stderr,
    # never stdout, so the handshake stays unambiguous.
    logging.basicConfig(filename=os.path.join(LOG_DIR, "server.log"), level=logging.DEBUG,
        format="%(asctime)s pid=%(process)d [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("buckaroo.server")
    log.info("Server starting — port=%d open_browser=%s pid=%d", args.port, not args.no_browser, os.getpid())

    sockets, bound_port, app = bind_and_make_app(port=args.port,
        open_browser=not args.no_browser, datasets=args.datasets)
    server = tornado.httpserver.HTTPServer(app)
    server.add_sockets(sockets)

    # Handshake line for parent-process supervisors (Tauri sidecar, etc.).
    # stdout was reconfigured to line_buffering above, so the newline flushes.
    print(f"BUCKAROO_PORT={bound_port}")
    log.info("Server listening on http://127.0.0.1:%d", bound_port)

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
