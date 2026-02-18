import argparse
import logging
import os

import tornado.ioloop

from buckaroo.server.app import make_app

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Buckaroo data server")
    parser.add_argument("--port", type=int, default=8700, help="Port to listen on")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on /load")
    args = parser.parse_args()

    # Configure server-side logging to file with timestamps
    logging.basicConfig(
        filename=os.path.join(LOG_DIR, "server.log"),
        level=logging.DEBUG,
        format="%(asctime)s pid=%(process)d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("buckaroo.server")
    log.info("Server starting — port=%d open_browser=%s pid=%d", args.port, not args.no_browser, os.getpid())

    app = make_app(port=args.port, open_browser=not args.no_browser)
    app.listen(args.port)
    log.info("Server listening on http://localhost:%d", args.port)

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
