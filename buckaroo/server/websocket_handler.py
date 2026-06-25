import copy
import json
import logging
import os
import traceback
from contextlib import nullcontext
from urllib.parse import urlparse

import tornado.websocket

from buckaroo.pluggable_analysis_framework import perf_log
from buckaroo.server import telemetry
from buckaroo.server.data_loading import (handle_infinite_request, handle_infinite_request_buckaroo, handle_infinite_request_lazy, get_buckaroo_display_state)
from buckaroo.server.session import build_state_message


def _handle_infinite_request_xorq(xorq_dataflow, payload_args, search_string=""):
    """Lazy delegate so the server stays importable without buckaroo[xorq]."""
    from buckaroo.server.xorq_loading import handle_infinite_request_xorq
    return handle_infinite_request_xorq(xorq_dataflow, payload_args, search_string=search_string)


log = logging.getLogger("buckaroo.server.websocket")

_BUCKAROO_DEBUG = os.environ.get("BUCKAROO_DEBUG", "").lower() in ("1", "true")

# Fields in buckaroo_state that drive *dataflow* changes; mutations to
# any of these rebuild the dataflow and rebroadcast to every client.
# ``search_string`` is deliberately NOT here — it's per-client typing
# state owned by the handler instance (#851).
_DATAFLOW_FIELDS = ("post_processing", "cleaning_method", "quick_command_args")


class DataStreamHandler(tornado.websocket.WebSocketHandler):
    def open(self, session_id):
        self.session_id = session_id
        # Per-client live search term (#838, fix for #851/cross-client
        # pollution). Used only by the row-fetch filter and the per-client
        # highlight overlay below — never broadcast, never stored on the
        # session.
        self.search_string = ""
        sessions = self.application.settings["sessions"]
        sessions.add_ws_client(session_id, self)

        # Send initial state if session already has data loaded.
        # search_string="" — fresh connection, no per-client typing yet.
        session = sessions.get(session_id)
        if session and (session.df is not None or session.ldf is not None or session.xorq_dataflow is not None):
            self.write_message(json.dumps(build_state_message(session, search_string=self.search_string)))

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

            # Decide up front whether the dataflow path will run, so we
            # don't both (a) send a per-client overlay AND (b) broadcast
            # an initial_state in the same turn. The broadcast already
            # carries any highlight_phrase that ``quick_command_args.search``
            # produced via cleaning_sd, so the overlay would be redundant
            # (and tests/clients that read one message back would see two).
            dataflow_changed = any(old_state.get(f) != new_state.get(f) for f in _DATAFLOW_FIELDS)

            # Per-client live search (#838 / #851). Update self; if no
            # dataflow change is coming, send a targeted highlight overlay
            # to this client only. Never touches the session, never broadcasts.
            new_search = new_state.get("search_string", "")
            new_search = new_search if isinstance(new_search, str) else ""
            if self.search_string != new_search:
                self.search_string = new_search
                if not dataflow_changed:
                    self._send_highlight_overlay(session)

            # Skip if no effective change to the fields that drive the dataflow.
            if not dataflow_changed:
                log.debug("buckaroo_state_change no-op session=%s — skipping rebroadcast", self.session_id)
                return

            # Propagate changes to the dataflow (mirrors BuckarooWidgetBase._buckaroo_state)
            if old_state.get("post_processing") != new_state.get("post_processing"):
                dataflow.post_processing_method = new_state.get("post_processing", "")
            if old_state.get("cleaning_method") != new_state.get("cleaning_method"):
                dataflow.cleaning_method = new_state.get("cleaning_method", "")
            if old_state.get("quick_command_args") != new_state.get("quick_command_args"):
                dataflow.quick_command_args = new_state.get("quick_command_args", {})

            # Re-extract state from the dataflow — same helper works for both
            # ServerDataflow and XorqServerDataflow (verified by probe).
            buckaroo_state = get_buckaroo_display_state(dataflow)
            session.df_display_args = buckaroo_state["df_display_args"]
            session.df_data_dict = buckaroo_state["df_data_dict"]
            session.df_meta = buckaroo_state["df_meta"]
            # Strip search_string before snapshotting onto the session — it
            # belongs to this client only (#851), so a future client that
            # connects shouldn't inherit it via build_state_message.
            session.buckaroo_state = {k: v for k, v in new_state.items() if k != "search_string"}
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

            # Broadcast updated state to all connected clients. Each
            # client gets its own search_string re-injected so a
            # dataflow rebuild from one tab doesn't silently clear the
            # search box on another (or on the typing client itself).
            for client in list(session.ws_clients):
                try:
                    msg = build_state_message(session,
                        search_string=getattr(client, "search_string", ""))
                    client.write_message(json.dumps(msg))
                except Exception:
                    session.ws_clients.discard(client)
        except Exception:
            tb = traceback.format_exc()
            log.error("buckaroo_state_change error session=%s: %s", self.session_id, tb)
            err: dict = {"type": "error", "error_code": "state_change_error", "message": "Failed to apply state change"}
            if _BUCKAROO_DEBUG:
                err["details"] = tb
            self.write_message(json.dumps(err))

    def _send_highlight_overlay(self, session):
        """Send this client an ``initial_state`` with highlight_phrase
        injected into every string-column ``displayer_args`` so live-typed
        matches highlight in the grid (#851).

        Per-client because ``search_string`` is per-client — another
        client's term must not bleed into this one's highlight, and a
        broadcast initial_state would clobber every other input box. We
        deep-copy ``session.df_display_args`` so the overlay never
        mutates the shared session snapshot.

        Empty term clears any prior highlight by sending the pristine
        df_display_args back. Skipped when no display config is loaded
        yet — the upcoming ``initial_state`` on first load will be
        unhighlighted, which is correct (search starts empty).
        """
        if not session.df_display_args:
            return
        term = self.search_string
        overlay = copy.deepcopy(session.df_display_args)
        for dva in overlay.values():
            dvc = (dva or {}).get("df_viewer_config") or {}
            for col in dvc.get("column_config", []) or []:
                disp = col.get("displayer_args")
                if not isinstance(disp, dict) or disp.get("displayer") != "string":
                    continue
                if term:
                    disp["highlight_phrase"] = [term]
                else:
                    disp.pop("highlight_phrase", None)

        # Pass self.search_string so the overlay's buckaroo_state
        # round-trips the typed term back to this client (Codex P1 on
        # #854 — without it the JS clears the search box on every
        # keystroke).
        msg = build_state_message(session, search_string=self.search_string)
        msg["df_display_args"] = overlay
        try:
            self.write_message(json.dumps(msg))
        except Exception:
            log.debug("highlight overlay write failed for session=%s", self.session_id)

    def _handle_infinite_request(self, payload_args):
        sessions = self.application.settings["sessions"]
        session = sessions.get(self.session_id)

        if not session or (session.df is None and session.ldf is None and session.xorq_dataflow is None):
            self.write_message(json.dumps({"type": "infinite_resp", "key": payload_args, "length": 0,
                "error_info": "No data loaded for this session"}))
            return

        def _dispatch(pa):
            # search_string is the per-CLIENT live-typed filter (#838 /
            # #851) — read off self so two clients sharing the session
            # don't fight over each other's input. Passed alongside
            # payload_args rather than mixed into it so the WS-level
            # row-fetch contract (start/end/sort) stays untouched and
            # each backend can apply the filter in its native
            # expression layer.
            search = self.search_string or ""
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

        # First infinite_request for this session = time-to-first-rows. The
        # first pull and its eager second window together make up the initial
        # screen load, so each gets its own span (window_to_parquet encode +
        # frame send), keyed by session= so they line up with the
        # firstpull.load_expr spans. Fire them when perf logging is on OR
        # telemetry is wired for this session (#943), and bind the telemetry
        # sink for just this initial load — genuine per-scroll row spans are
        # deferred (v2).
        not_seen = not session._perf_first_payload_seen
        tele_sink = (telemetry.make_http_sink(session.telemetry_url)
                     if (session.telemetry_url and not_seen) else None)
        first_payload = not_seen and (perf_log.enabled() or tele_sink is not None)
        try:
            with perf_log.telemetry_context(self.session_id, tele_sink):
                first_span = (perf_log.perf_span("firstpull.ws_first_payload", session=self.session_id)
                              if first_payload else nullcontext())
                with first_span:
                    resp_msg, parquet_bytes = _dispatch(payload_args)
                    # Two-frame sequence: JSON text frame, then binary Parquet frame
                    self.write_message(json.dumps(resp_msg))
                    if parquet_bytes:
                        self.write_message(parquet_bytes, binary=True)
                if first_payload:
                    session._perf_first_payload_seen = True

                # Eager second window (#896). Instrument it as its OWN span
                # rather than letting its work ride inside the first pull's
                # context (where it would surface only as an unlabeled nested
                # window_to_parquet record). Gated on first_payload too, so
                # later per-scroll requests stay uninstrumented (v2).
                second_pa = payload_args.get("second_request")
                if second_pa:
                    second_span = (perf_log.perf_span("firstpull.ws_second_payload", session=self.session_id)
                                   if first_payload else nullcontext())
                    with second_span:
                        resp2, parquet2 = _dispatch(second_pa)
                        self.write_message(json.dumps(resp2))
                        if parquet2:
                            self.write_message(parquet2, binary=True)
        except Exception:
            tb = traceback.format_exc()
            log.error("infinite_request error session=%s: %s", self.session_id, tb)
            self.write_message(json.dumps({"type": "infinite_resp", "key": payload_args, "length": 0,
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
