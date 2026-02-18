import json
import logging
import os
import platform
import sys
import time
import traceback

import tornado.web

from buckaroo.server.data_loading import (
    load_file, get_metadata, get_display_state,
    create_dataflow, get_buckaroo_display_state,
)
from buckaroo.server.focus import find_or_create_session_window

log = logging.getLogger("buckaroo.server.handlers")

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")

CRITICAL_STATIC_FILES = [
    "standalone.js",
    "standalone.css",
    "compiled.css",
    "widget.js",
]


def _get_static_file_info(static_path: str) -> dict:
    """Check existence and size of critical static files."""
    result = {}
    for name in CRITICAL_STATIC_FILES:
        fpath = os.path.join(static_path, name)
        if os.path.isfile(fpath):
            result[name] = {"exists": True, "size_bytes": os.path.getsize(fpath)}
        else:
            result[name] = {"exists": False, "size_bytes": 0}
    return result


def _check_dependency(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


class HealthHandler(tornado.web.RequestHandler):
    def get(self):
        import buckaroo
        start_time = self.application.settings.get("server_start_time", 0)
        static_path = self.application.settings.get("static_path", "")
        self.write({
            "status": "ok",
            "version": getattr(buckaroo, "__version__", "unknown"),
            "pid": os.getpid(),
            "started": start_time,
            "uptime_s": round(time.time() - start_time, 1),
            "static_files": _get_static_file_info(static_path),
        })


class DiagnosticsHandler(tornado.web.RequestHandler):
    def get(self):
        import tornado as _tornado
        import buckaroo

        static_path = self.application.settings.get("static_path", "")
        start_time = self.application.settings.get("server_start_time", 0)

        self.write({
            "status": "ok",
            "pid": os.getpid(),
            "uptime_s": round(time.time() - start_time, 1),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "buckaroo_version": getattr(buckaroo, "__version__", "unknown"),
            "tornado_version": _tornado.version,
            "static_path": os.path.abspath(static_path),
            "static_files": _get_static_file_info(static_path),
            "log_dir": LOG_DIR,
            "log_files": _list_log_files(),
            "dependencies": {
                "tornado": _check_dependency("tornado"),
                "pandas": _check_dependency("pandas"),
                "pyarrow": _check_dependency("pyarrow"),
                "fastparquet": _check_dependency("fastparquet"),
                "mcp": _check_dependency("mcp"),
                "polars": _check_dependency("polars"),
            },
        })


def _list_log_files() -> list:
    """List log files in the buckaroo log directory."""
    try:
        if os.path.isdir(LOG_DIR):
            return [
                {"name": f, "size_bytes": os.path.getsize(os.path.join(LOG_DIR, f))}
                for f in sorted(os.listdir(LOG_DIR))
                if f.endswith(".log")
            ]
    except OSError:
        pass
    return []


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

        # Push full state to connected WebSocket clients so they pick up
        # the new dataset without a page reload.  This mirrors the
        # initial_state message sent by DataStreamHandler.open().
        if session.ws_clients:
            state_msg = {
                "type": "initial_state",
                "metadata": metadata,
                "df_display_args": session.df_display_args,
                "df_data_dict": session.df_data_dict,
                "df_meta": session.df_meta,
                "mode": session.mode,
            }
            if session.mode == "buckaroo":
                state_msg["buckaroo_state"] = session.buckaroo_state
                state_msg["buckaroo_options"] = session.buckaroo_options
                state_msg["command_config"] = session.command_config
                state_msg["operation_results"] = session.operation_results
                state_msg["operations"] = session.operations
            push_msg = json.dumps(state_msg)
            for client in list(session.ws_clients):
                try:
                    client.write_message(push_msg)
                except Exception:
                    session.ws_clients.discard(client)

        # Browser management: find existing window or create one (disabled in tests)
        # reload_if_found=True triggers a page reload when the tab already
        # exists so it picks up the newly-loaded dataset.
        browser_action = "disabled"
        if self.application.settings.get("open_browser", True):
            port = self.application.settings.get("port", 8888)
            browser_action = find_or_create_session_window(session_id, port, reload_if_found=True)

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
        html, body, #root { margin: 0; padding: 0; width: 100%; height: 100vh; background: #181D1F; }
        /* Flex utility classes used by components */
        .flex { display: flex; }
        .flex-col { flex-direction: column; }
        /* orig-df uses "flex flex-row" but layout must be column (status bar on top, table below) */
        .orig-df.flex-row { flex-direction: column; }
        /* Match Jupyter's .cell-output-ipywidget-background gap removal */
        .status-bar { margin-bottom: 0; }
        .df-viewer { margin-top: 0; }
        .df-viewer .theme-hanger { margin-top: -12px; }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="module" src="/static/standalone.js"></script>
</body>
</html>
"""
