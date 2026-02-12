import argparse

import tornado.ioloop

from buckaroo.server.app import make_app


def main():
    parser = argparse.ArgumentParser(description="Buckaroo data server")
    parser.add_argument("--port", type=int, default=8700, help="Port to listen on")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser on start")
    args = parser.parse_args()

    app = make_app(port=args.port)
    app.listen(args.port)
    print(f"Buckaroo server running at http://localhost:{args.port}")

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
