import json
import traceback

import tornado.websocket

from buckaroo.server.data_loading import handle_infinite_request


class DataStreamHandler(tornado.websocket.WebSocketHandler):
    def open(self, session_id):
        self.session_id = session_id
        sessions = self.application.settings["sessions"]
        sessions.add_ws_client(session_id, self)

        # Send initial state if session already has data loaded
        session = sessions.get(session_id)
        if session and session.df is not None:
            self.write_message(json.dumps({
                "type": "initial_state",
                "metadata": session.metadata,
                "df_display_args": session.df_display_args,
                "df_data_dict": session.df_data_dict,
                "df_meta": session.df_meta,
            }))

    def on_message(self, message):
        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            self.write_message(json.dumps({"type": "error", "error": "Invalid JSON"}))
            return

        if msg.get("type") == "infinite_request":
            self._handle_infinite_request(msg.get("payload_args", {}))

    def _handle_infinite_request(self, payload_args):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)

        if not session or session.df is None:
            self.write_message(json.dumps({
                "type": "infinite_resp",
                "key": payload_args,
                "data": [],
                "length": 0,
                "error_info": "No data loaded for this session",
            }))
            return

        try:
            resp_msg, parquet_bytes = handle_infinite_request(session.df, payload_args)
            # Two-frame sequence: JSON text frame, then binary Parquet frame
            self.write_message(json.dumps(resp_msg))
            self.write_message(parquet_bytes, binary=True)

            # Handle second_request (eager loading)
            second_pa = payload_args.get("second_request")
            if second_pa:
                resp2, parquet2 = handle_infinite_request(session.df, second_pa)
                self.write_message(json.dumps(resp2))
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
