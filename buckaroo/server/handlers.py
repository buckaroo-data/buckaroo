import json
import logging
import os
import time
import traceback

import tornado.web

from buckaroo.server.data_loading import (
    load_file, get_metadata, get_display_state,
    create_dataflow, get_buckaroo_display_state,
)
from buckaroo.server.focus import find_or_create_session_window

log = logging.getLogger("buckaroo.server.handlers")


class HealthHandler(tornado.web.RequestHandler):
    def get(self):
        start_time = self.application.settings.get("server_start_time", 0)
        self.write({
            "status": "ok",
            "pid": os.getpid(),
            "started": start_time,
            "uptime_s": round(time.time() - start_time, 1),
        })


class LoadHandler(tornado.web.RequestHandler):
    async def post(self):
        try:
            body = json.loads(self.request.body)
        except (json.JSONDecodeError, TypeError):
            self.set_status(400)
            self.write({"error": "Invalid JSON body"})
            return

        if not isinstance(body, dict):
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

        mode = body.get("mode", "viewer")

        sessions = self.application.settings["sessions"]
        session = sessions.get_or_create(session_id, path)
        session.df = df
        session.mode = mode
        metadata = get_metadata(df, path)
        session.metadata = metadata

        if mode == "buckaroo":
            # Run the full Buckaroo analysis pipeline
            dataflow = create_dataflow(df)
            session.dataflow = dataflow
            buckaroo_state = get_buckaroo_display_state(dataflow)
            session.df_display_args = buckaroo_state["df_display_args"]
            session.df_data_dict = buckaroo_state["df_data_dict"]
            session.df_meta = buckaroo_state["df_meta"]
            session.buckaroo_state = buckaroo_state["buckaroo_state"]
            session.buckaroo_options = buckaroo_state["buckaroo_options"]
            session.command_config = buckaroo_state["command_config"]
            session.operation_results = buckaroo_state["operation_results"]
            session.operations = buckaroo_state["operations"]
        else:
            # Compute minimal display state for the JS client
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

        # Browser management: find existing window or create one (disabled in tests)
        browser_action = "disabled"
        if self.application.settings.get("open_browser", True):
            port = self.application.settings.get("port", 8888)
            browser_action = find_or_create_session_window(session_id, port)

        log.info("load session=%s path=%s rows=%d browser=%s", session_id, path, metadata["rows"], browser_action)

        self.write({
            "session": session_id,
            "server_pid": os.getpid(),
            "browser_action": browser_action,
            **metadata,
        })


class SessionPageHandler(tornado.web.RequestHandler):
    def get(self, session_id):
        self.set_header("Content-Type", "text/html")
        self.write(SESSION_HTML.replace("__SESSION_ID__", session_id))


SESSION_HTML = """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Buckaroo — __SESSION_ID__</title>
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
