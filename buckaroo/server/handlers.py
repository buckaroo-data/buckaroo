import json
import traceback
import webbrowser

import tornado.web

from buckaroo.server.data_loading import load_file, get_metadata, get_display_state
from buckaroo.server.focus import focus_browser_tab


class HealthHandler(tornado.web.RequestHandler):
    def get(self):
        self.write({"status": "ok"})


class LoadHandler(tornado.web.RequestHandler):
    async def post(self):
        try:
            body = json.loads(self.request.body)
        except (json.JSONDecodeError, TypeError):
            self.set_status(400)
            self.write({"error": "Invalid JSON body"})
            return

        session_id = body.get("session")
        path = body.get("path")

        if not session_id or not path:
            self.set_status(400)
            self.write({"error": "Missing 'session' or 'path'"})
            return

        try:
            df = load_file(path)
        except FileNotFoundError:
            self.set_status(404)
            self.write({"error": f"File not found: {path}"})
            return
        except ValueError as e:
            self.set_status(400)
            self.write({"error": str(e)})
            return
        except Exception:
            self.set_status(500)
            self.write({"error": traceback.format_exc()})
            return

        sessions = self.application.settings["sessions"]
        session = sessions.get_or_create(session_id, path)
        session.df = df
        metadata = get_metadata(df, path)
        session.metadata = metadata

        # Compute display state for the JS client
        display_state = get_display_state(df, path)
        session.df_display_args = display_state["df_display_args"]
        session.df_data_dict = display_state["df_data_dict"]
        session.df_meta = display_state["df_meta"]

        # Push metadata to connected WebSocket clients
        push_msg = json.dumps({"type": "metadata", **metadata})
        for client in list(session.ws_clients):
            try:
                client.write_message(push_msg)
            except Exception:
                session.ws_clients.discard(client)

        # Browser management: open or focus (disabled in tests)
        if self.application.settings.get("open_browser", True):
            port = self.application.settings.get("port", 8888)
            if not session.ws_clients:
                # No browser tab connected yet — open one
                url = f"http://localhost:{port}/s/{session_id}"
                webbrowser.open(url)
            else:
                # Tab already exists — bring it to front
                focus_browser_tab(session_id, port)

        self.write({"session": session_id, **metadata})


class SessionPageHandler(tornado.web.RequestHandler):
    def get(self, session_id):
        self.set_header("Content-Type", "text/html")
        self.write(SESSION_HTML)


SESSION_HTML = """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Buckaroo</title>
    <link rel="stylesheet" href="/static/compiled.css">
    <link rel="stylesheet" href="/static/standalone.css">
    <style>
        html, body, #root { margin: 0; padding: 0; width: 100%; height: 100vh; }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="module" src="/static/standalone.js"></script>
</body>
</html>
"""
