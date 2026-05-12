import argparse
import logging
import os
import sys

import tornado.httpserver
import tornado.ioloop
import tornado.netutil

from buckaroo.server.app import make_app

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def bind_and_make_app(port: int, open_browser: bool):
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
    app = make_app(port=bound_port, open_browser=open_browser)
    return sockets, bound_port, app


def main():
    parser = argparse.ArgumentParser(description="Buckaroo data server")
    parser.add_argument("--port", type=int, default=8700, help="Port to listen on (0 = random)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on /load")
    parser.add_argument("--stdio-control", action="store_true",
        help="Exit when stdin closes. Used by parent supervisors (Tauri) to "
        "guarantee the sidecar dies when the parent does — closing stdin is "
        "more reliable than process-tree teardown across platforms.")
    args = parser.parse_args()

    # Line-buffer stdout so the BUCKAROO_PORT handshake reaches a parent supervisor
    # immediately when stdout is a pipe (Tauri/PyInstaller).
    sys.stdout.reconfigure(line_buffering=True)

    if args.stdio_control:
        # Background thread blocks on stdin; when the parent closes the pipe,
        # the read returns empty and we exit. macOS/Linux only in v1; Windows
        # has different stdin-pipe semantics and is deferred with the platform.
        import threading
        def _stdin_watchdog():
            try:
                while sys.stdin.read(1):
                    pass
            except Exception:
                pass
            os._exit(0)
        threading.Thread(target=_stdin_watchdog, daemon=True).start()

    # Configure server-side logging to file with timestamps. Logs go to file + stderr,
    # never stdout, so the handshake stays unambiguous.
    logging.basicConfig(filename=os.path.join(LOG_DIR, "server.log"), level=logging.DEBUG,
        format="%(asctime)s pid=%(process)d [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("buckaroo.server")
    log.info("Server starting — port=%d open_browser=%s pid=%d", args.port, not args.no_browser, os.getpid())

    sockets, bound_port, app = bind_and_make_app(port=args.port, open_browser=not args.no_browser)
    server = tornado.httpserver.HTTPServer(app)
    server.add_sockets(sockets)

    # Handshake line for parent-process supervisors (Tauri sidecar, etc.).
    print(f"BUCKAROO_PORT={bound_port}", flush=True)
    log.info("Server listening on http://127.0.0.1:%d", bound_port)

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
