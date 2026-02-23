import json
import traceback

import tornado.websocket

from buckaroo.server.data_loading import (
    handle_infinite_request,
    handle_infinite_request_buckaroo,
    handle_infinite_request_lazy,
    get_buckaroo_display_state,
)


class DataStreamHandler(tornado.websocket.WebSocketHandler):
    def open(self, session_id):
        self.session_id = session_id
        sessions = self.application.settings["sessions"]
        sessions.add_ws_client(session_id, self)

        # Send initial state if session already has data loaded
        session = sessions.get(session_id)
        if session and (session.df is not None or session.ldf is not None):
            msg = {
                "type": "initial_state",
                "metadata": session.metadata,
                "prompt": session.prompt,
                "df_display_args": session.df_display_args,
                "df_data_dict": session.df_data_dict,
                "df_meta": session.df_meta,
                "mode": session.mode,
            }
            if session.mode == "buckaroo":
                msg["buckaroo_state"] = session.buckaroo_state
                msg["buckaroo_options"] = session.buckaroo_options
                msg["command_config"] = session.command_config
                msg["operation_results"] = session.operation_results
                msg["operations"] = session.operations
            self.write_message(json.dumps(msg))

    def on_message(self, message):
        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            self.write_message(json.dumps({"type": "error", "error": "Invalid JSON"}))
            return

        msg_type = msg.get("type")
        if msg_type == "infinite_request":
            self._handle_infinite_request(msg.get("payload_args", {}))
        elif msg_type == "buckaroo_state_change":
            self._handle_buckaroo_state_change(msg.get("new_state", {}))

    def _handle_buckaroo_state_change(self, new_state):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)
        if not session or session.mode != "buckaroo" or not session.dataflow:
            return

        old_state = session.buckaroo_state
        try:
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
            update_msg = json.dumps({
                "type": "initial_state",
                "df_display_args": session.df_display_args,
                "df_data_dict": session.df_data_dict,
                "df_meta": session.df_meta,
                "mode": session.mode,
                "buckaroo_state": session.buckaroo_state,
                "buckaroo_options": session.buckaroo_options,
                "command_config": session.command_config,
                "operation_results": session.operation_results,
                "operations": session.operations,
            })
            for client in list(session.ws_clients):
                try:
                    client.write_message(update_msg)
                except Exception:
                    session.ws_clients.discard(client)
        except Exception:
            self.write_message(json.dumps({
                "type": "error",
                "error": traceback.format_exc(),
            }))

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
            self.write_message(json.dumps({
                "type": "infinite_resp",
                "key": payload_args,
                "data": [],
                "length": 0,
                "error_info": traceback.format_exc(),
            }))

    def on_close(self):
        sessions = self.application.settings["sessions"]
        sessions.remove_ws_client(self.session_id, self)

    def check_origin(self, origin):
        # Allow connections from any origin (local dev tool)
        return True
