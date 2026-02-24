import json
import logging
import os
import traceback
from urllib.parse import urlparse

import tornado.websocket

from buckaroo.server.data_loading import (
    handle_infinite_request,
    handle_infinite_request_buckaroo,
    handle_infinite_request_lazy,
    get_buckaroo_display_state,
)
from buckaroo.server.session import build_state_message

log = logging.getLogger("buckaroo.server.websocket")

_BUCKAROO_DEBUG = os.environ.get("BUCKAROO_DEBUG", "").lower() in ("1", "true")

# Fields in buckaroo_state that drive dataflow changes; others are ignored.
_DATAFLOW_FIELDS = ("post_processing", "cleaning_method", "quick_command_args")


class DataStreamHandler(tornado.websocket.WebSocketHandler):
    def open(self, session_id):
        self.session_id = session_id
        sessions = self.application.settings["sessions"]
        sessions.add_ws_client(session_id, self)

        # Send initial state if session already has data loaded
        session = sessions.get(session_id)
        if session and (session.df is not None or session.ldf is not None):
            self.write_message(json.dumps(build_state_message(session)))

    def on_message(self, message):
        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            self.write_message(json.dumps({
                "type": "error",
                "error_code": "invalid_json",
                "message": "Invalid JSON",
            }))
            return

        msg_type = msg.get("type")
        if msg_type == "infinite_request":
            self._handle_infinite_request(msg.get("payload_args", {}))
        elif msg_type == "buckaroo_state_change":
            self._handle_buckaroo_state_change(msg.get("new_state") or {})

    def _handle_buckaroo_state_change(self, new_state):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)
        if not session or session.mode != "buckaroo" or not session.dataflow:
            return

        old_state = session.buckaroo_state

        try:
            # Validate payload type before any attribute access.
            if not isinstance(new_state, dict):
                raise ValueError(f"new_state must be a dict, got {type(new_state).__name__}")

            # Skip if no effective change to the fields that drive the dataflow.
            if all(old_state.get(f) == new_state.get(f) for f in _DATAFLOW_FIELDS):
                log.debug(
                    "buckaroo_state_change no-op session=%s — skipping rebroadcast",
                    self.session_id,
                )
                return

            # Propagate changes to the dataflow (mirrors BuckarooWidgetBase._buckaroo_state)
            if old_state.get("post_processing") != new_state.get("post_processing"):
                session.dataflow.post_processing_method = new_state.get("post_processing", "")
            if old_state.get("cleaning_method") != new_state.get("cleaning_method"):
                session.dataflow.cleaning_method = new_state.get("cleaning_method", "")
            if old_state.get("quick_command_args") != new_state.get("quick_command_args"):
                session.dataflow.quick_command_args = new_state.get("quick_command_args", {})

            # Re-extract state from the dataflow
            buckaroo_state = get_buckaroo_display_state(session.dataflow)
            session.df_display_args = buckaroo_state["df_display_args"]
            session.df_data_dict = buckaroo_state["df_data_dict"]
            session.df_meta = buckaroo_state["df_meta"]
            session.buckaroo_state = new_state
            session.buckaroo_options = buckaroo_state["buckaroo_options"]
            session.command_config = buckaroo_state["command_config"]

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
            err: dict = {
                "type": "error",
                "error_code": "state_change_error",
                "message": "Failed to apply state change",
            }
            if _BUCKAROO_DEBUG:
                err["details"] = tb
            self.write_message(json.dumps(err))

    def _handle_infinite_request(self, payload_args):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)

        if not session or (session.df is None and session.ldf is None):
            self.write_message(json.dumps({
                "type": "infinite_resp",
                "key": payload_args,
                "data": [],
                "length": 0,
                "error_info": "No data loaded for this session",
            }))
            return

        try:
            if session.mode == "lazy" and session.ldf is not None:
                resp_msg, parquet_bytes = handle_infinite_request_lazy(
                    session.ldf, session.orig_to_rw, session.rw_to_orig,
                    session.metadata.get("rows", 0), payload_args,
                )
            elif session.mode == "buckaroo" and session.dataflow:
                resp_msg, parquet_bytes = handle_infinite_request_buckaroo(
                    session.dataflow, payload_args
                )
            else:
                resp_msg, parquet_bytes = handle_infinite_request(session.df, payload_args)

            # Two-frame sequence: JSON text frame, then binary Parquet frame
            self.write_message(json.dumps(resp_msg))
            if parquet_bytes:
                self.write_message(parquet_bytes, binary=True)

            # Handle second_request (eager loading)
            second_pa = payload_args.get("second_request")
            if second_pa:
                if session.mode == "lazy" and session.ldf is not None:
                    resp2, parquet2 = handle_infinite_request_lazy(
                        session.ldf, session.orig_to_rw, session.rw_to_orig,
                        session.metadata.get("rows", 0), second_pa,
                    )
                elif session.mode == "buckaroo" and session.dataflow:
                    resp2, parquet2 = handle_infinite_request_buckaroo(
                        session.dataflow, second_pa
                    )
                else:
                    resp2, parquet2 = handle_infinite_request(session.df, second_pa)
                self.write_message(json.dumps(resp2))
                if parquet2:
                    self.write_message(parquet2, binary=True)
        except Exception:
            tb = traceback.format_exc()
            log.error("infinite_request error session=%s: %s", self.session_id, tb)
            self.write_message(json.dumps({
                "type": "infinite_resp",
                "key": payload_args,
                "data": [],
                "length": 0,
                "error_info": tb if _BUCKAROO_DEBUG else "Request failed",
            }))

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
