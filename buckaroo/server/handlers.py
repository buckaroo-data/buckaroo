import json
import logging
import os
import platform
import sys
import time
import traceback
import uuid

import tornado.escape
import tornado.web

from buckaroo.server.data_loading import (load_file, get_metadata, get_display_state, create_dataflow, get_buckaroo_display_state, load_file_lazy, get_metadata_lazy, get_display_state_lazy)
from buckaroo.compare import col_join_dfs
from buckaroo.df_util import old_col_new_col
from buckaroo.server.focus import find_or_create_session_window
from buckaroo.server.session import build_state_message

log = logging.getLogger("buckaroo.server.handlers")

_BUCKAROO_DEBUG = os.environ.get("BUCKAROO_DEBUG", "").lower() in ("1", "true")

LOG_DIR = os.path.join(os.path.expanduser("~"), ".buckaroo", "logs")


def _parse_startup_timeout() -> float:
    try:
        return float(os.environ.get("BUCKAROO_STARTUP_TIMEOUT", "5.0"))
    except ValueError:
        log.warning("BUCKAROO_STARTUP_TIMEOUT is not a valid number; using default 5.0s")
        return 5.0

CRITICAL_STATIC_FILES = ["standalone.js", "standalone.css", "compiled.css", "widget.js"]


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
        self.write({"status": "ok", "version": getattr(buckaroo, "__version__", "unknown"), "pid": os.getpid(),
            "started": start_time, "uptime_s": round(time.time() - start_time, 1),
            "static_files": _get_static_file_info(static_path)})


class DiagnosticsHandler(tornado.web.RequestHandler):
    def get(self):
        import tornado as _tornado
        import buckaroo

        static_path = self.application.settings.get("static_path", "")
        start_time = self.application.settings.get("server_start_time", 0)
        sessions = self.application.settings.get("sessions")

        session_info: dict = {}
        if sessions is not None:
            session_info = {"active": sessions.active_session_count, "total_evicted": sessions.total_evicted_count,
                "ttl_s": sessions._ttl_s, "eviction_interval_s": sessions._eviction_interval_s}

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
            "sessions": session_info,
            "startup_timeout_s": _parse_startup_timeout(),
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
        """Validate and extract session_id, path, mode, prompt, no_browser, component_config, backend from request.

        Returns (session_id, path, mode, prompt, no_browser, component_config, backend) or a tuple of Nones on error.

        ``session`` is optional — when omitted the server mints a UUID and
        returns it in the response. Lets Tauri/Electron-style hosts call /load
        without inventing session IDs.
        """
        session_id = body.get("session")
        path = body.get("path")

        if not path:
            self.set_status(400)
            self.write({"error": "Missing 'path'"})
            return None, None, None, None, None, None, None

        if not session_id:
            session_id = uuid.uuid4().hex

        mode = body.get("mode", "viewer")
        prompt = body.get("prompt", "")
        no_browser = bool(body.get("no_browser", False))
        component_config = body.get("component_config")
        # ``backend`` is mode="buckaroo"-only: "pandas" (default) builds a
        # ServerDataflow against pandas; "polars" builds a PolarsServerDataflow.
        # Validated/branched in ``post`` — silently passed through here so a
        # bad value surfaces as a 400 from the loader, not a TypeError.
        backend = str(body.get("backend", "pandas")).lower()
        return session_id, path, mode, prompt, no_browser, component_config, backend

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
        """Push updated state to all connected WebSocket clients.

        Also resets each client's live ``search_string`` (#851): the
        dataset just changed, so a term carried over from the previous
        load would silently filter the new one.
        """
        log.info("push_state path=%s ws_clients=%d", metadata.get("filename", "?"), len(session.ws_clients))
        if not session.ws_clients:
            return

        for client in list(session.ws_clients):
            try:
                # Reset per-client live search first (dataset changed),
                # then build the msg so the injected ``buckaroo_state``
                # mirrors the post-reset value.
                client.search_string = ""
                msg = build_state_message(session, metadata=metadata,
                    search_string=client.search_string)
                client.write_message(json.dumps(msg))
            except Exception:
                session.ws_clients.discard(client)

    def _handle_browser_window(self, session_id: str) -> str:
        """Handle browser window management."""
        if not self.application.settings.get("open_browser", True):
            return "disabled"

        port = self.application.settings["port"]
        return find_or_create_session_window(session_id, port, reload_if_found=True)

    def _load_polars_with_error_handling(self, path: str):
        """Eager polars load for ``backend='polars'``. Errors share the
        same shape as the pandas loader so the response surface is
        identical from the client's POV."""
        try:
            from buckaroo.server.data_loading_polars import load_file_polars, get_metadata_polars
            df = load_file_polars(path)
            metadata = get_metadata_polars(df, path)
            return df, metadata
        except FileNotFoundError:
            self.set_status(404)
            self.write({"error_code": "file_not_found", "message": f"File not found: {path}"})
            return None, None
        except ImportError:
            self.set_status(400)
            self.write({"error_code": "missing_dependency",
                "message": "backend='polars' requires polars to be installed"})
            return None, None
        except ValueError as e:
            self.set_status(400)
            self.write({"error_code": "invalid_file", "message": str(e)})
            return None, None
        except Exception:
            tb = traceback.format_exc()
            log.error("polars load error path=%s: %s", path, tb)
            resp: dict = {"error_code": "load_error", "message": "Failed to load file"}
            if _BUCKAROO_DEBUG:
                resp["details"] = tb
            self.set_status(500)
            self.write(resp)
            return None, None

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
            self.write({"error_code": "file_not_found", "message": f"File not found: {path}"})
            return None, None
        except ValueError as e:
            self.set_status(400)
            self.write({"error_code": "invalid_file", "message": str(e)})
            return None, None
        except Exception:
            tb = traceback.format_exc()
            log.error("load error path=%s: %s", path, tb)
            resp: dict = {"error_code": "load_error", "message": "Failed to load file"}
            if _BUCKAROO_DEBUG:
                resp["details"] = tb
            self.set_status(500)
            self.write(resp)
            return None, None

    async def post(self):
        body = self._parse_request_body()
        if body is None:
            return

        session_id, path, mode, prompt, no_browser, component_config, backend = self._validate_request(body)
        if session_id is None:
            return

        # ``backend`` only affects mode="buckaroo". Reject early so a
        # mismatched lazy/viewer request doesn't silently look fine.
        if backend not in ("pandas", "polars"):
            self.set_status(400)
            self.write({"error_code": "invalid_backend",
                "message": f"backend must be 'pandas' or 'polars', got {backend!r}"})
            return
        if backend == "polars" and mode != "buckaroo":
            self.set_status(400)
            self.write({"error_code": "invalid_backend",
                "message": "backend='polars' is only valid with mode='buckaroo'"})
            return

        column_config_overrides = body.get("column_config_overrides")
        extra_grid_config = body.get("extra_grid_config")
        init_sd = body.get("init_sd")

        sessions = self.application.settings["sessions"]
        session = sessions.get_or_create(session_id, path)
        session.mode = mode
        # Loading via /load is pandas or polars — clear any xorq state left
        # by a prior /load_expr on the same session so WS dispatch routes
        # to the new dataflow rather than a stale xorq one.
        session.backend = backend
        session.xorq_dataflow = None
        session.expr = None
        session.prompt = prompt
        if component_config:
            session.component_config = component_config

        # Load data in appropriate mode
        if backend == "polars" and mode == "buckaroo":
            file_obj, metadata = self._load_polars_with_error_handling(path)
        else:
            file_obj, metadata = self._load_file_with_error_handling(path, is_lazy=(mode == "lazy"))
        if file_obj is None:
            return

        if mode == "lazy":
            self._load_lazy_polars(session, path, file_obj, metadata)
        else:
            session.df = file_obj
            session.metadata = metadata
            if mode == "buckaroo":
                if backend == "polars":
                    from buckaroo.server.data_loading_polars import create_polars_dataflow
                    dataflow = create_polars_dataflow(file_obj,
                        column_config_overrides=column_config_overrides,
                        extra_grid_config=extra_grid_config, init_sd=init_sd)
                else:
                    dataflow = create_dataflow(file_obj,
                        column_config_overrides=column_config_overrides,
                        extra_grid_config=extra_grid_config, init_sd=init_sd)
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

        # Merge component_config into df_display_args if provided
        if component_config and session.df_display_args:
            for key in session.df_display_args:
                dvc = session.df_display_args[key].get("df_viewer_config")
                if dvc is not None:
                    dvc["component_config"] = {
                        **dvc.get("component_config", {}),
                        **component_config,
                    }

        # Notify connected clients and open browser
        self._push_state_to_clients(session, metadata)
        browser_action = "skipped" if no_browser else self._handle_browser_window(session_id)

        log.info("load session=%s path=%s rows=%d browser=%s", session_id, path, metadata["rows"], browser_action)

        self.write({"session": session_id, "server_pid": os.getpid(), "browser_action": browser_action, **metadata})


class LoadExprHandler(tornado.web.RequestHandler):
    """POST /load_expr — load a xorq/ibis expression from a build dir
    and serve it via the xorq-backed buckaroo dataflow.

    Counterpart to ``LoadHandler`` for the xorq path. Reads
    ``build_dir`` (the output of ``xorq build`` / ``xo.build_expr``)
    rather than a file path, since the xorq widget's value is
    push-down query execution against the underlying backend, not
    paging over a materialised parquet.

    ``mode`` on the session is still ``"buckaroo"`` (the frontend
    renders identically); ``session.backend = "xorq"`` discriminates
    inside the WS dispatch."""

    def _parse_request_body(self) -> dict | None:
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

    async def post(self):
        body = self._parse_request_body()
        if body is None:
            return

        build_dir = body.get("build_dir")
        if not build_dir:
            self.set_status(400)
            self.write({"error": "Missing 'build_dir'"})
            return

        session_id = body.get("session") or uuid.uuid4().hex
        no_browser = bool(body.get("no_browser", False))
        force_reload = bool(body.get("force_reload", False))

        # Config-bearing fields that change how the result is computed or
        # rendered. If the caller passes any of these on a warm POST we must
        # re-run the pipeline — returning cached metadata would silently
        # ignore the new config.
        has_config = any(body.get(k) for k in (
            "component_config", "column_config_overrides", "extra_grid_config",
            "init_sd", "skip_stat_columns"))

        # Short-circuit: if this session is already loaded with the same
        # build_dir (and no new config was supplied), skip the expensive
        # pipeline and return cached metadata. Only fires when the caller
        # explicitly passes back a session_id from a prior response
        # (UUID-generated ids are always new). Pass force_reload=true — or any
        # config-bearing field — to bypass this and re-run the full pipeline.
        sessions = self.application.settings["sessions"]
        existing = sessions.get(session_id)
        if (not force_reload and not has_config and existing
                and existing.build_dir == build_dir and existing.metadata):
            if no_browser or not self.application.settings.get("open_browser", True):
                browser_action = "skipped"
            else:
                port = self.application.settings["port"]
                browser_action = find_or_create_session_window(
                    session_id, port, reload_if_found=True)
            self.write({"session": session_id, "server_pid": os.getpid(),
                "browser_action": browser_action, **existing.metadata})
            return

        try:
            from buckaroo.server import xorq_loading
        except ImportError:
            self.set_status(501)
            self.write({"error_code": "xorq_not_installed",
                "message": "xorq is not installed on this server. "
                "Install with `pip install buckaroo[xorq]`."})
            return

        prompt = body.get("prompt", "")
        component_config = body.get("component_config")
        column_config_overrides = body.get("column_config_overrides")
        extra_grid_config = body.get("extra_grid_config")
        init_sd = body.get("init_sd")
        # Columns whose summary stats are supplied via init_sd and must not be
        # recomputed (e.g. a diff reusing each source column's stats).
        skip_stat_columns = body.get("skip_stat_columns")

        project_root = body.get("project_root")
        cache_storage_path = body.get("cache_storage_path")

        try:
            expr = xorq_loading.load_expr_build_dir(build_dir)
            extra_klasses = (
                xorq_loading.load_project_stat_klasses(project_root)
                + xorq_loading.load_project_post_processing_klasses(project_root)
                + xorq_loading.load_project_display_klasses(project_root)
                if project_root else [])
            xorq_dataflow = xorq_loading.XorqServerDataflow(
                expr, skip_main_serial=True, extra_klasses=extra_klasses,
                cache_storage_path=cache_storage_path,
                column_config_overrides=column_config_overrides,
                extra_grid_config=extra_grid_config, init_sd=init_sd,
                skip_stat_columns=skip_stat_columns)
            metadata = xorq_loading.get_xorq_metadata(xorq_dataflow, build_dir)
        except FileNotFoundError:
            self.set_status(404)
            self.write({"error_code": "build_dir_not_found",
                "message": f"Build directory not found: {build_dir}"})
            return
        except Exception:
            tb = traceback.format_exc()
            log.error("load_expr error build_dir=%s: %s", build_dir, tb)
            resp: dict = {"error_code": "load_expr_error",
                "message": "Failed to load xorq expression"}
            if _BUCKAROO_DEBUG:
                resp["details"] = tb
            self.set_status(500)
            self.write(resp)
            return

        sessions = self.application.settings["sessions"]
        session = sessions.get_or_create(session_id, build_dir)
        session.mode = "buckaroo"
        session.backend = "xorq"
        session.expr = expr
        session.build_dir = build_dir
        session.project_root = project_root
        session.xorq_dataflow = xorq_dataflow
        # Clear pandas-side state left by a prior /load on the same
        # session so WS dispatch can no longer reach a stale dataflow.
        session.df = None
        session.dataflow = None
        session.ldf = None
        session.metadata = metadata
        session.prompt = prompt
        if component_config:
            session.component_config = component_config

        session.df_display_args = xorq_dataflow.df_display_args
        session.df_data_dict = xorq_dataflow.df_data_dict
        session.df_meta = xorq_dataflow.df_meta
        session.buckaroo_state = {
            "cleaning_method": "", "post_processing": "", "sampled": False,
            "show_commands": False, "df_display": "main",
            "search_string": "", "quick_command_args": {}}
        session.buckaroo_options = xorq_dataflow.buckaroo_options
        session.command_config = xorq_dataflow.command_config
        session.operation_results = {
            "transformed_df": {"schema": {"fields": []}, "data": []},
            "generated_py_code": "# server mode"}
        session.operations = []

        if component_config and session.df_display_args:
            for key in session.df_display_args:
                dvc = session.df_display_args[key].get("df_viewer_config")
                if dvc is not None:
                    dvc["component_config"] = {
                        **dvc.get("component_config", {}),
                        **component_config}

        if session.ws_clients:
            for client in list(session.ws_clients):
                try:
                    # Reset per-client live search (#851): a term from
                    # the prior expression would silently filter the new one.
                    client.search_string = ""
                    msg = build_state_message(session, metadata=metadata,
                        search_string=client.search_string)
                    client.write_message(json.dumps(msg))
                except Exception:
                    session.ws_clients.discard(client)

        if no_browser or not self.application.settings.get("open_browser", True):
            browser_action = "skipped"
        else:
            port = self.application.settings["port"]
            browser_action = find_or_create_session_window(session_id, port, reload_if_found=True)

        log.info("load_expr session=%s build_dir=%s rows=%d backend=xorq",
            session_id, build_dir, metadata["rows"])
        self.write({"session": session_id, "server_pid": os.getpid(),
            "browser_action": browser_action, **metadata})


class LoadCompareHandler(tornado.web.RequestHandler):
    """POST /load_compare — load two files, diff them via col_join_dfs, and
    serve the merged result with diff styling applied."""

    def _parse_request_body(self) -> dict:
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

    def _validate_request(self, body: dict):
        """Return (session_id, path1, path2, join_columns, how, no_browser)
        or all-Nones on error."""
        session_id = body.get("session")
        path1 = body.get("path1")
        path2 = body.get("path2")
        join_columns = body.get("join_columns")

        if not session_id or not path1 or not path2 or not join_columns:
            self.set_status(400)
            self.write({"error": "Missing required field(s): session, path1, path2, join_columns"})
            return None, None, None, None, None, None

        how = body.get("how", "outer")
        no_browser = bool(body.get("no_browser", False))
        return session_id, path1, path2, join_columns, how, no_browser

    def _load_file(self, path: str):
        """Load a single file, writing error response on failure.
        Returns DataFrame or None."""
        try:
            return load_file(path)
        except FileNotFoundError:
            self.set_status(404)
            self.write({"error_code": "file_not_found", "message": f"File not found: {path}"})
            return None
        except ValueError as e:
            self.set_status(400)
            self.write({"error_code": "invalid_file", "message": str(e)})
            return None
        except Exception:
            tb = traceback.format_exc()
            log.error("load error path=%s: %s", path, tb)
            resp: dict = {"error_code": "load_error", "message": f"Failed to load file: {path}"}
            if _BUCKAROO_DEBUG:
                resp["details"] = tb
            self.set_status(500)
            self.write(resp)
            return None

    async def post(self):
        body = self._parse_request_body()
        if body is None:
            return

        session_id, path1, path2, join_columns, how, no_browser = self._validate_request(body)
        if session_id is None:
            return

        df1 = self._load_file(path1)
        if df1 is None:
            return
        df2 = self._load_file(path2)
        if df2 is None:
            return

        try:
            merged_df, column_config_overrides, eqs = col_join_dfs(df1, df2, join_columns, how)
        except ValueError as e:
            self.set_status(400)
            self.write({"error_code": "compare_error", "message": str(e)})
            return
        except Exception:
            tb = traceback.format_exc()
            log.error("compare error: %s", tb)
            resp: dict = {"error_code": "compare_error", "message": "Failed to compare files"}
            if _BUCKAROO_DEBUG:
                resp["details"] = tb
            self.set_status(500)
            self.write(resp)
            return

        # Build display state from merged DataFrame
        display_state = get_display_state(merged_df, path1)

        # Apply column_config_overrides with name translation
        orig_to_renamed = dict(old_col_new_col(merged_df))
        column_config = display_state["df_display_args"]["main"]["df_viewer_config"]["column_config"]

        for cc_entry in column_config:
            orig_name = cc_entry["header_name"]
            override = column_config_overrides.get(orig_name)
            if override is None:
                continue
            for key, value in override.items():
                if key == "merge_rule":
                    cc_entry["merge_rule"] = value
                elif key in ("tooltip_config", "color_map_config"):
                    translated = dict(value)
                    if "val_column" in translated:
                        translated["val_column"] = orig_to_renamed.get(
                            translated["val_column"], translated["val_column"])
                    cc_entry[key] = translated
                else:
                    cc_entry[key] = value

        # Store session state
        sessions = self.application.settings["sessions"]
        session = sessions.get_or_create(session_id, path1)
        session.df = merged_df
        session.metadata = {"path": path1, "path2": path2, "rows": len(merged_df),
            "columns": [{"name": str(c), "dtype": str(merged_df[c].dtype)} for c in merged_df.columns]}
        session.df_display_args = display_state["df_display_args"]
        session.df_data_dict = display_state["df_data_dict"]
        session.df_meta = display_state["df_meta"]
        session.mode = "viewer"

        # Push to WebSocket clients
        if session.ws_clients:
            for client in list(session.ws_clients):
                try:
                    # Reset per-client live search (#851).
                    client.search_string = ""
                    msg = build_state_message(session,
                        search_string=client.search_string)
                    client.write_message(json.dumps(msg))
                except Exception:
                    session.ws_clients.discard(client)

        # Browser window
        if no_browser or not self.application.settings.get("open_browser", True):
            browser_action = "skipped"
        else:
            port = self.application.settings.get("port", 8888)
            browser_action = find_or_create_session_window(session_id, port, reload_if_found=True)

        log.info("load_compare session=%s path1=%s path2=%s rows=%d",
            session_id, path1, path2, len(merged_df))

        self.write({"session": session_id, "server_pid": os.getpid(), "browser_action": browser_action,
            "rows": len(merged_df), "columns": [str(c) for c in merged_df.columns], "eqs": eqs})


class ReloadExprHandler(tornado.web.RequestHandler):
    """POST /reload_expr/<session_id> — refresh post-processing and stat
    klasses on a live xorq session without restarting the server.

    Re-scans ``<project_root>/stats/`` and ``<project_root>/post_processing/``
    for the session's stored project root, rebuilds the ``XorqServerDataflow``
    with the fresh klass list, and broadcasts the updated ``command_config``
    and ``buckaroo_options`` to all open WebSocket clients. The expression
    and its cached stats are reused — no re-execute against the data backend.

    Returns 404 when the session does not exist, 400 when it is not a xorq
    session or has no project_root recorded, 501 when xorq is not installed."""

    async def post(self, session_id):
        sessions = self.application.settings["sessions"]
        session = sessions.get(session_id)
        if session is None:
            self.set_status(404)
            self.write({"error_code": "session_not_found",
                "message": f"Session not found: {session_id}"})
            return

        if session.backend != "xorq" or session.xorq_dataflow is None:
            self.set_status(400)
            self.write({"error_code": "not_xorq_session",
                "message": "Session is not a xorq session"})
            return

        if not session.project_root:
            self.set_status(400)
            self.write({"error_code": "no_project_root",
                "message": "Session has no project_root — pass project_root to /load_expr first"})
            return

        try:
            from buckaroo.server import xorq_loading
        except ImportError:
            self.set_status(501)
            self.write({"error_code": "xorq_not_installed",
                "message": "xorq is not installed on this server. "
                "Install with `pip install buckaroo[xorq]`."})
            return

        try:
            extra_klasses = (
                xorq_loading.load_project_stat_klasses(session.project_root)
                + xorq_loading.load_project_post_processing_klasses(session.project_root)
                + xorq_loading.load_project_display_klasses(session.project_root))
            xorq_dataflow = xorq_loading.XorqServerDataflow(
                session.expr, skip_main_serial=True, extra_klasses=extra_klasses)
        except Exception:
            tb = traceback.format_exc()
            log.error("reload_expr error session=%s: %s", session_id, tb)
            resp: dict = {"error_code": "reload_expr_error",
                "message": "Failed to reload xorq klasses"}
            if _BUCKAROO_DEBUG:
                resp["details"] = tb
            self.set_status(500)
            self.write(resp)
            return

        # Replay the session's active buckaroo state onto the new dataflow so
        # a user who had selected a post-processing method or set
        # cleaning_method / quick_command_args before the reload doesn't
        # silently get unfiltered results while the UI still shows their
        # previous selection.
        bs = session.buckaroo_state
        if bs.get("post_processing"):
            xorq_dataflow.post_processing_method = bs["post_processing"]
        if bs.get("cleaning_method"):
            xorq_dataflow.cleaning_method = bs["cleaning_method"]
        if bs.get("quick_command_args"):
            xorq_dataflow.quick_command_args = bs["quick_command_args"]

        refreshed = get_buckaroo_display_state(xorq_dataflow)
        session.xorq_dataflow = xorq_dataflow
        session.df_display_args = refreshed["df_display_args"]
        session.df_data_dict = refreshed["df_data_dict"]
        session.df_meta = refreshed["df_meta"]
        session.buckaroo_options = refreshed["buckaroo_options"]
        session.command_config = refreshed["command_config"]

        if session.component_config and session.df_display_args:
            for key in session.df_display_args:
                dvc = session.df_display_args[key].get("df_viewer_config")
                if dvc is not None:
                    dvc["component_config"] = {
                        **dvc.get("component_config", {}),
                        **session.component_config}

        for client in list(session.ws_clients):
            try:
                msg = build_state_message(session,
                    search_string=getattr(client, "search_string", ""))
                client.write_message(json.dumps(msg))
            except Exception:
                session.ws_clients.discard(client)

        klass_count = len(extra_klasses)
        log.info("reload_expr session=%s project_root=%s klasses=%d",
            session_id, session.project_root, klass_count)
        self.write({"session": session_id, "klasses_loaded": klass_count})


def _render_engine_bar(datasets: list) -> tuple:
    """Render the engine-dropdown HTML + JS-side dataset config for the
    demo session page.

    Returns ``(bar_html, datasets_json)``. ``bar_html`` is the inline
    ``<div id="engine-bar">…</div>`` block, or the empty string when no
    datasets are configured (so a vanilla server doesn't ship a dead
    UI). ``datasets_json`` is the JSON-encoded list the inline ``<script>``
    consumes — kept on a separate substitution so it stays alongside the
    options it drives even when ``bar_html`` is empty.

    See issue #811: the previous design hard-coded
    ``/tmp/restaurant-complaints-pandas.parquet`` etc. inline; now the
    operator supplies them via ``--dataset NAME=KIND:PATH``.

    Uses ``tornado.escape.json_encode`` (not ``json.dumps``) because the
    output is embedded inline in a ``<script>`` block: a target string
    containing ``</script>`` would otherwise break out of the tag.
    ``json_encode`` replaces ``</`` with ``<\\/``."""
    datasets_json = tornado.escape.json_encode(datasets or [])
    if not datasets:
        return "", datasets_json
    options = ["<option value=\"\">— switch dataset —</option>"]
    for idx, ds in enumerate(datasets):
        label = tornado.escape.xhtml_escape(ds["label"])
        kind = tornado.escape.xhtml_escape(ds["kind"])
        target = tornado.escape.xhtml_escape(ds["target"])
        options.append(
            f"<option value=\"{idx}\" data-kind=\"{kind}\" data-target=\"{target}\">"
            f"{label} ({kind})</option>")
    bar = (
        "<div id=\"engine-bar\" style=\"padding: 4px 10px; font-family: sans-serif; "
        "font-size: 12px; color: #ccc; background: #1f1f24; "
        "border-bottom: 1px solid #333; flex-shrink: 0;\">"
        "Dataset: "
        "<select id=\"engine-select\" style=\"background: #2a2a30; color: #ddd; "
        "border: 1px solid #444; padding: 2px 6px; margin-left: 6px;\">"
        + "".join(options) + "</select>"
        "<span id=\"engine-status\" style=\"margin-left: 12px; color: #888;\"></span>"
        "</div>")
    return bar, datasets_json


class SessionPageHandler(tornado.web.RequestHandler):
    def get(self, session_id):
        self.set_header("Content-Type", "text/html")
        self.set_header("Cache-Control", "no-cache")
        import buckaroo
        ver = getattr(buckaroo, "__version__", "0")
        datasets = self.application.settings.get("datasets", []) or []
        engine_bar, datasets_json = _render_engine_bar(datasets)
        html = (SESSION_HTML
            .replace("__SESSION_ID__", session_id)
            .replace("__VERSION__", ver)
            .replace("__ENGINE_BAR__", engine_bar)
            .replace("__DATASETS_JSON__", datasets_json))
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
    __ENGINE_BAR__
    <div id="root"></div>
    <script id="buckaroo-datasets" type="application/json">__DATASETS_JSON__</script>
    <script>
    // Engine dropdown wiring for /s/<session>. Reads the operator-supplied
    // dataset list from the JSON ``<script>`` above (populated by
    // ``_render_engine_bar``) and adds any ``?pd=&pl=&xq=`` query-string
    // overrides as extra ``(from URL)`` options so URL-driven workflows
    // survive. The dropdown element is only emitted when at least one
    // operator dataset is registered — see issue #811.
    (function () {
        const SESSION_ID = "__SESSION_ID__";
        const DATASETS = JSON.parse(
            document.getElementById("buckaroo-datasets").textContent || "[]");
        const qs = new URLSearchParams(window.location.search);
        const qsOverrides = [];
        if (qs.get("pd")) qsOverrides.push({label: "(from URL) pandas", kind: "pandas", target: qs.get("pd")});
        if (qs.get("pl")) qsOverrides.push({label: "(from URL) lazy", kind: "lazy", target: qs.get("pl")});
        if (qs.get("xq")) qsOverrides.push({label: "(from URL) xorq", kind: "xorq", target: qs.get("xq")});
        const ENTRIES = DATASETS.concat(qsOverrides);
        if (ENTRIES.length === 0) return;

        // Find or inject the bar. The server emits it whenever it has
        // operator-supplied datasets; we inject it when only QS overrides
        // exist. Either way the rest of this function works against the
        // same select element.
        let sel = document.getElementById("engine-select");
        if (!sel) {
            const bar = document.createElement("div");
            bar.id = "engine-bar";
            bar.style.cssText = "padding: 4px 10px; font-family: sans-serif; font-size: 12px; color: #ccc; background: #1f1f24; border-bottom: 1px solid #333; flex-shrink: 0;";
            bar.innerHTML = 'Dataset: <select id="engine-select" style="background: #2a2a30; color: #ddd; border: 1px solid #444; padding: 2px 6px; margin-left: 6px;"></select><span id="engine-status" style="margin-left: 12px; color: #888;"></span>';
            document.body.insertBefore(bar, document.getElementById("root"));
            sel = document.getElementById("engine-select");
        }
        const statusEl = document.getElementById("engine-status");

        // Rebuild options from ENTRIES so the DOM and our index space stay
        // in lockstep — regardless of whether the server pre-rendered the
        // operator datasets or we just injected an empty select.
        sel.innerHTML = '<option value="">— switch dataset —</option>';
        ENTRIES.forEach((ds, i) => {
            const opt = document.createElement("option");
            opt.value = String(i);
            opt.dataset.kind = ds.kind;
            opt.dataset.target = ds.target;
            opt.textContent = `${ds.label} (${ds.kind})`;
            sel.appendChild(opt);
        });

        sel.addEventListener("change", async (e) => {
            const idx = e.target.value;
            if (idx === "") return;
            const ds = ENTRIES[parseInt(idx, 10)];
            if (!ds) return;
            const url = ds.kind === "xorq" ? "/load_expr" : "/load";
            const body = {session: SESSION_ID, no_browser: true};
            if (ds.kind === "xorq") {
                body.build_dir = ds.target;
            } else {
                body.path = ds.target;
                body.mode = ds.kind === "lazy" ? "lazy" : "buckaroo";
            }
            const t0 = performance.now();
            statusEl.textContent = `loading ${ds.label}…`;
            try {
                const r = await fetch(url, {method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(body)});
                const dt = Math.round(performance.now() - t0);
                if (r.ok) {
                    const d = await r.json();
                    statusEl.textContent = `${ds.label} loaded (${d.rows ?? "?"} rows, ${dt} ms) — reloading…`;
                    // The widget reads its initial state on WS open. Reload
                    // forces a clean reconnection rather than reasoning
                    // about deep widget-level swap.
                    setTimeout(() => window.location.reload(), 600);
                } else {
                    const err = await r.text();
                    statusEl.textContent = `${ds.label} failed (${r.status}): ${err.slice(0, 200)}`;
                }
            } catch (ex) {
                statusEl.textContent = `${ds.label} error: ${ex.message}`;
            }
        });
    })();
    </script>
    <script type="module" src="/static/standalone.js?v=__VERSION__"></script>
</body>
</html>
"""
