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
    load_file_lazy, get_metadata_lazy, get_display_state_lazy,
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
    def _parse_request_body(self) -> dict:
        """Parse and validate JSON request body."""
        try:
            body = json.loads(self.request.body)
        except (json.JSONDecodeError, TypeError):
            self.set_status(400)
            self.write({"error": "Invalid JSON body"})
            return None

        if not isinstance(body, dict):
            self.set_status(400)
            self.write({"error": "Invalid JSON body"})
            return None

        return body

    def _validate_request(self, body: dict) -> tuple:
        """Validate and extract session_id, path, mode, prompt, and no_browser from request.

        Returns (session_id, path, mode, prompt, no_browser) or a tuple of Nones on error.
        """
        session_id = body.get("session")
        path = body.get("path")

        if not session_id or not path:
            self.set_status(400)
            self.write({"error": "Missing 'session' or 'path'"})
            return None, None, None, None, None

        mode = body.get("mode", "viewer")
        prompt = body.get("prompt", "")
        no_browser = bool(body.get("no_browser", False))
        return session_id, path, mode, prompt, no_browser

    def _load_lazy_polars(self, session, path: str, ldf, metadata: dict):
        """Set up lazy polars session state."""
        display_state, orig_to_rw, rw_to_orig = get_display_state_lazy(ldf)
        display_state["df_meta"]["total_rows"] = metadata["rows"]

        session.ldf = ldf
        session.orig_to_rw = orig_to_rw
        session.rw_to_orig = rw_to_orig
        session.metadata = metadata
        session.df_display_args = display_state["df_display_args"]
        session.df_data_dict = display_state["df_data_dict"]
        session.df_meta = display_state["df_meta"]
        return True

    def _push_state_to_clients(self, session, metadata: dict):
        """Push updated state to all connected WebSocket clients."""
        log.info("push_state path=%s ws_clients=%d", metadata.get("filename", "?"), len(session.ws_clients))
        if not session.ws_clients:
            return

        state_msg = {
            "type": "initial_state",
            "metadata": metadata,
            "prompt": session.prompt,
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

    def _handle_browser_window(self, session_id: str) -> str:
        """Handle browser window management."""
        if not self.application.settings.get("open_browser", True):
            return "disabled"

        port = self.application.settings.get("port", 8888)
        return find_or_create_session_window(session_id, port, reload_if_found=True)

    def _load_file_with_error_handling(self, path: str, is_lazy: bool):
        """Load file and handle errors. Returns (file_obj, metadata) or (None, None)."""
        try:
            if is_lazy:
                ldf = load_file_lazy(path)
                metadata = get_metadata_lazy(ldf, path)
                return ldf, metadata
            else:
                df = load_file(path)
                metadata = get_metadata(df, path)
                return df, metadata
        except FileNotFoundError:
            self.set_status(404)
            self.write({"error": f"File not found: {path}"})
            return None, None
        except ValueError as e:
            self.set_status(400)
            self.write({"error": str(e)})
            return None, None
        except Exception:
            self.set_status(500)
            self.write({"error": traceback.format_exc()})
            return None, None

    async def post(self):
        body = self._parse_request_body()
        if body is None:
            return

        session_id, path, mode, prompt, no_browser = self._validate_request(body)
        if session_id is None:
            return

        sessions = self.application.settings["sessions"]
        session = sessions.get_or_create(session_id, path)
        session.mode = mode
        session.prompt = prompt

        # Load data in appropriate mode
        file_obj, metadata = self._load_file_with_error_handling(path, is_lazy=(mode == "lazy"))
        if file_obj is None:
            return

        if mode == "lazy":
            self._load_lazy_polars(session, path, file_obj, metadata)
        else:
            session.df = file_obj
            session.metadata = metadata
            if mode == "buckaroo":
                dataflow = create_dataflow(file_obj)
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
                display_state = get_display_state(file_obj, path)
                session.df_display_args = display_state["df_display_args"]
                session.df_data_dict = display_state["df_data_dict"]
                session.df_meta = display_state["df_meta"]

        # Notify connected clients and open browser
        self._push_state_to_clients(session, metadata)
        browser_action = "skipped" if no_browser else self._handle_browser_window(session_id)

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
        self.set_header("Cache-Control", "no-cache")
        import buckaroo
        ver = getattr(buckaroo, "__version__", "0")
        html = SESSION_HTML.replace("__SESSION_ID__", session_id).replace("__VERSION__", ver)
        self.write(html)


SESSION_HTML = """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Buckaroo — __SESSION_ID__</title>
    <link rel="stylesheet" href="/static/compiled.css?v=__VERSION__">
    <link rel="stylesheet" href="/static/standalone.css?v=__VERSION__">
    <style>
        html, body { margin: 0; padding: 0; width: 100%; height: 100vh; background: #181d1f; }
        @media (prefers-color-scheme: light) { html, body { background: #fff; } }
        /* MCP standalone: fill the viewport */
        body { display: flex; flex-direction: column; }
        #filename-bar { padding: 4px 10px; font-family: sans-serif; font-size: 13px; color: #ccc; background: #222; border-bottom: 1px solid #333; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        #filename-bar:empty { display: none; }
        #prompt-bar { padding: 4px 10px; font-family: sans-serif; font-size: 12px; color: #999; background: #222; border-bottom: 1px solid #333; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        #prompt-bar:empty { display: none; }
        #root { flex: 1; display: flex; flex-direction: column; min-height: 0; margin-bottom: 20px; }
        .buckaroo_anywidget { flex: 1; display: flex; flex-direction: column; min-height: 0; }
        .dcf-root { flex: 1; display: flex; flex-direction: column; min-height: 0; }
        .orig-df { flex: 1; display: flex; flex-direction: column; min-height: 0; }
        .df-viewer { flex: 1; display: flex; flex-direction: column; min-height: 0; }
        /* Override inline height from heightStyle() — flex: 1 lets the grid fill
           the available space instead of using a fixed pixel height. */
        .df-viewer .theme-hanger { flex: 1 !important; overflow: hidden; }
        /* Flex utility classes used by components */
        .flex { display: flex; }
        .flex-col { flex-direction: column; }
        /* orig-df uses "flex flex-row" but layout must be column (status bar on top, table below) */
        .orig-df.flex-row { flex-direction: column; }
        /* Eliminate gap between status bar and main grid */
        .status-bar { margin-bottom: 0; }
        .status-bar .theme-hanger { margin-bottom: 0; }
        .status-bar .ag-root-wrapper { border-bottom: none !important; margin-bottom: 0; }
        .df-viewer { margin-top: 0; }
        .df-viewer .theme-hanger { margin-top: 0; }
        .df-viewer .ag-root-wrapper { margin-top: 0; }
    </style>
</head>
<body>
    <div id="filename-bar"></div>
    <div id="prompt-bar"></div>
    <div id="root"></div>
    <script type="module" src="/static/standalone.js?v=__VERSION__"></script>
</body>
</html>
"""
