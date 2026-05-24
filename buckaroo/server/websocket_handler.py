import json
import logging
import os
import traceback
from urllib.parse import urlparse

import tornado.websocket

from buckaroo.server.data_loading import (handle_infinite_request, handle_infinite_request_buckaroo, handle_infinite_request_lazy, get_buckaroo_display_state)
from buckaroo.server.session import build_state_message


def _handle_infinite_request_xorq(xorq_dataflow, payload_args, search_string=""):
    """Lazy delegate so the server stays importable without buckaroo[xorq]."""
    from buckaroo.server.xorq_loading import handle_infinite_request_xorq
    return handle_infinite_request_xorq(xorq_dataflow, payload_args, search_string=search_string)


log = logging.getLogger("buckaroo.server.websocket")

_BUCKAROO_DEBUG = os.environ.get("BUCKAROO_DEBUG", "").lower() in ("1", "true")

# Fields in buckaroo_state that drive dataflow changes; others are ignored.
# search_string lives here too — it doesn't touch the dataflow itself but
# the row-fetch dispatch reads ``session.search_string`` and applies a
# literal-contains filter before paginating (#838).
_DATAFLOW_FIELDS = ("post_processing", "cleaning_method", "quick_command_args", "search_string")


class DataStreamHandler(tornado.websocket.WebSocketHandler):
    def open(self, session_id):
        self.session_id = session_id
        sessions = self.application.settings["sessions"]
        sessions.add_ws_client(session_id, self)

        # Send initial state if session already has data loaded
        session = sessions.get(session_id)
        if session and (session.df is not None or session.ldf is not None or session.xorq_dataflow is not None):
            self.write_message(json.dumps(build_state_message(session)))

    def on_message(self, message):
        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            self.write_message(json.dumps({"type": "error", "error_code": "invalid_json", "message": "Invalid JSON"}))
            return

        msg_type = msg.get("type")
        if msg_type == "infinite_request":
            self._handle_infinite_request(msg.get("payload_args", {}))
        elif msg_type == "buckaroo_state_change":
            self._handle_buckaroo_state_change(msg.get("new_state") or {})

    def _handle_buckaroo_state_change(self, new_state):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)
        if not session or session.mode != "buckaroo":
            return
        dataflow = session.xorq_dataflow if session.backend == "xorq" else session.dataflow
        if dataflow is None:
            return

        old_state = session.buckaroo_state

        try:
            # Validate payload type before any attribute access.
            if not isinstance(new_state, dict):
                raise ValueError(f"new_state must be a dict, got {type(new_state).__name__}")

            # Skip if no effective change to the fields that drive the dataflow.
            if all(old_state.get(f) == new_state.get(f) for f in _DATAFLOW_FIELDS):
                log.debug("buckaroo_state_change no-op session=%s — skipping rebroadcast", self.session_id)
                return

            # Propagate changes to the dataflow (mirrors BuckarooWidgetBase._buckaroo_state)
            if old_state.get("post_processing") != new_state.get("post_processing"):
                dataflow.post_processing_method = new_state.get("post_processing", "")
            if old_state.get("cleaning_method") != new_state.get("cleaning_method"):
                dataflow.cleaning_method = new_state.get("cleaning_method", "")
            if old_state.get("quick_command_args") != new_state.get("quick_command_args"):
                dataflow.quick_command_args = new_state.get("quick_command_args", {})
            # search_string is stored on the session — the row-fetch
            # dispatch reads it instead of pushing it into the dataflow
            # (#838). Coerce non-string to "" so a malformed payload can't
            # crash the filter helpers downstream.
            new_search = new_state.get("search_string", "")
            session.search_string = new_search if isinstance(new_search, str) else ""

            # Re-extract state from the dataflow — same helper works for both
            # ServerDataflow and XorqServerDataflow (verified by probe).
            buckaroo_state = get_buckaroo_display_state(dataflow)
            session.df_display_args = buckaroo_state["df_display_args"]
            session.df_data_dict = buckaroo_state["df_data_dict"]
            session.df_meta = buckaroo_state["df_meta"]
            session.buckaroo_state = new_state
            session.buckaroo_options = buckaroo_state["buckaroo_options"]
            session.command_config = buckaroo_state["command_config"]

            # Re-apply component_config so theme settings survive state changes
            if session.component_config and session.df_display_args:
                for key in session.df_display_args:
                    dvc = session.df_display_args[key].get("df_viewer_config")
                    if dvc is not None:
                        dvc["component_config"] = {
                            **dvc.get("component_config", {}),
                            **session.component_config,
                        }

            # Broadcast updated state to all connected clients
            update_payload = json.dumps(build_state_message(session))
            for client in list(session.ws_clients):
                try:
                    client.write_message(update_payload)
                except Exception:
                    session.ws_clients.discard(client)
        except Exception:
            tb = traceback.format_exc()
            log.error("buckaroo_state_change error session=%s: %s", self.session_id, tb)
            err: dict = {"type": "error", "error_code": "state_change_error", "message": "Failed to apply state change"}
            if _BUCKAROO_DEBUG:
                err["details"] = tb
            self.write_message(json.dumps(err))

    def _handle_infinite_request(self, payload_args):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)

        if not session or (session.df is None and session.ldf is None and session.xorq_dataflow is None):
            self.write_message(json.dumps({"type": "infinite_resp", "key": payload_args, "data": [], "length": 0,
                "error_info": "No data loaded for this session"}))
            return

        def _dispatch(pa):
            # search_string is the per-session live-typed filter (#838) —
            # passed alongside payload_args rather than mixed into it so
            # the WS-level row-fetch contract (start/end/sort) stays
            # untouched and each backend can apply the filter in its
            # native expression layer.
            search = session.search_string or ""
            if session.mode == "lazy" and session.ldf is not None:
                return handle_infinite_request_lazy(session.ldf, session.orig_to_rw,
                    session.rw_to_orig, session.metadata.get("rows", 0), pa)
            if session.mode == "buckaroo" and session.backend == "xorq" and session.xorq_dataflow:
                return _handle_infinite_request_xorq(session.xorq_dataflow, pa, search_string=search)
            if session.mode == "buckaroo" and session.backend == "polars" and session.dataflow:
                from buckaroo.server.data_loading_polars import handle_infinite_request_buckaroo_polars
                return handle_infinite_request_buckaroo_polars(session.dataflow, pa, search_string=search)
            if session.mode == "buckaroo" and session.dataflow:
                return handle_infinite_request_buckaroo(session.dataflow, pa, search_string=search)
            return handle_infinite_request(session.df, pa)

        try:
            resp_msg, parquet_bytes = _dispatch(payload_args)
            # Two-frame sequence: JSON text frame, then binary Parquet frame
            self.write_message(json.dumps(resp_msg))
            if parquet_bytes:
                self.write_message(parquet_bytes, binary=True)

            # Handle second_request (eager loading)
            second_pa = payload_args.get("second_request")
            if second_pa:
                resp2, parquet2 = _dispatch(second_pa)
                self.write_message(json.dumps(resp2))
                if parquet2:
                    self.write_message(parquet2, binary=True)
        except Exception:
            tb = traceback.format_exc()
            log.error("infinite_request error session=%s: %s", self.session_id, tb)
            self.write_message(json.dumps({"type": "infinite_resp", "key": payload_args, "data": [], "length": 0,
                "error_info": tb if _BUCKAROO_DEBUG else "Request failed"}))

    def on_close(self):
        sessions = self.application.settings["sessions"]
        sessions.remove_ws_client(self.session_id, self)

    def check_origin(self, origin):
        # Allow connections from any origin — this server is local-only by design
        # and not intended for network exposure. Set BUCKAROO_STRICT_ORIGIN=1 to
        # restrict to localhost origins if needed.
        if os.environ.get("BUCKAROO_STRICT_ORIGIN", "").lower() in ("1", "true"):
            try:
                hostname = urlparse(origin).hostname
            except Exception:
                return False
            return hostname in ("localhost", "127.0.0.1")
        return True
