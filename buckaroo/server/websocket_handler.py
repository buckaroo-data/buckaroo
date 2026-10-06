import copy
import json
import logging
import os
import traceback
from contextlib import nullcontext

import tornado.websocket

from buckaroo.pluggable_analysis_framework import perf_log
from buckaroo.server.data_loading import (handle_infinite_request, handle_infinite_request_buckaroo, handle_infinite_request_lazy, get_buckaroo_display_state)
from buckaroo.server.security import AuthMixin, LocalHostCheckMixin, is_valid_session_id, origin_is_allowed
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


class DataStreamHandler(AuthMixin, LocalHostCheckMixin, tornado.websocket.WebSocketHandler):
    def prepare(self):
        # super().prepare() runs the Host check then the token check (both
        # may finish() with 403). Then refuse a malformed session id before
        # the WS upgrade so it never reaches the dispatch — the upgrade fails
        # with 403 rather than opening a socket we immediately close.
        super().prepare()
        if self._finished:
            return
        session_id = self.path_args[0] if self.path_args else None
        if not is_valid_session_id(session_id):
            log.warning("refused WS upgrade for invalid session id: %r", session_id)
            self.set_status(403)
            self.finish()

    def check_origin(self, origin):
        # Same-origin (the standalone /s/ page) plus the configured embedder
        # allowlist. Replaces the previously permissive policy; the token is
        # still the primary gate. A missing Origin (non-browser) is allowed.
        return origin_is_allowed(origin, self.settings.get("port"),
            self.settings.get("allow_origins", ()))

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
            # state_seq (#998): the client's own counter for this change,
            # echoed back as reply_seq on the initial_state it gets so it
            # can drop a reply that an overlapping later change superseded.
            # Optional; a client that sends none gets none back.
            self._handle_buckaroo_state_change(msg.get("new_state") or {}, state_seq=msg.get("state_seq"))

    def _handle_buckaroo_state_change(self, new_state, state_seq=None):
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
            # an initial_state in the same turn. Each client's copy of the
            # broadcast carries its own highlight, so the overlay would be
            # redundant (and tests/clients that read one message back would
            # see two).
            dataflow_changed = any(old_state.get(f) != new_state.get(f) for f in _DATAFLOW_FIELDS)

            # Per-client live search (#838 / #851). Recorded on self only:
            # never on the session, never broadcast.
            new_search = new_state.get("search_string", "")
            new_search = new_search if isinstance(new_search, str) else ""
            search_changed = self.search_string != new_search
            if search_changed:
                self.search_string = new_search

            # Skip if no effective change to the fields that drive the dataflow.
            if not dataflow_changed:
                # A new search term gets this client its highlight overlay.
                # A numbered change gets an answer whatever it changed: the
                # client drops a reply older than its latest change, so a
                # no-op change that follows a dataflow change would otherwise
                # leave the earlier reply dropped and nothing newer to apply
                # (#998).
                if search_changed or state_seq is not None:
                    self._send_client_state(session, new_state, reply_seq=state_seq)
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
            # search box on another (or on the typing client itself), and
            # its own live-search highlight, so the rebuilt display config
            # doesn't drop it.
            # Only the originating client gets reply_seq (#998): the
            # others made no change, so every copy is current for them.
            for client in list(session.ws_clients):
                try:
                    search = getattr(client, "search_string", "")
                    msg = build_state_message(session, search_string=search,
                        reply_seq=state_seq if client is self else None)
                    msg["df_display_args"] = self._with_highlight(session.df_display_args, search)
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
            # A numbered change is answered even when it fails (#998): the
            # client has dropped the reply to its previous change as stale,
            # so the error alone would leave it on the data from before
            # both. The reply is the session's current data with the
            # change's own buckaroo_state, as every numbered reply is: the
            # session's would revert a search box that holds the failed
            # term, and the box would send it again.
            if state_seq is not None:
                self._send_client_state(session, new_state if isinstance(new_state, dict) else old_state,
                    reply_seq=state_seq)

    @staticmethod
    def _with_highlight(df_display_args, term):
        """``df_display_args`` with ``term`` as the ``highlight_phrase`` of
        every string column, as a deep copy so the shared session snapshot
        is never mutated. With no ``term`` it is returned as it is, so the
        highlight a committed ``quick_command_args.search`` put there
        stays."""
        if not term or not df_display_args:
            return df_display_args
        overlay = copy.deepcopy(df_display_args)
        for dva in overlay.values():
            dvc = (dva or {}).get("df_viewer_config") or {}
            for col in dvc.get("column_config", []) or []:
                disp = col.get("displayer_args")
                if isinstance(disp, dict) and disp.get("displayer") == "string":
                    disp["highlight_phrase"] = [term]
        return overlay

    def _send_client_state(self, session, buckaroo_state, reply_seq=None):
        """Send this client alone an ``initial_state``: the session's
        current data, ``buckaroo_state`` with this client's search term, and
        its live-search highlight (#851). It answers a change that reran no
        dataflow (a new search term, or a numbered change that touched
        nothing) and a numbered change that failed, so it never touches
        the session or reaches another client.

        ``buckaroo_state`` is the change's own. The session records one
        only on a dataflow change, so the session's would put back
        ``show_commands``, ``df_display`` and ``sampled``. The search term
        is re-injected so the reply doesn't clear the search box (Codex P1
        on #854). ``reply_seq`` is the change's ``state_seq`` (#998), so the
        client drops this reply if it has sent a later change.
        """
        msg = build_state_message(session, search_string=self.search_string, reply_seq=reply_seq)
        msg["buckaroo_state"] = {**buckaroo_state, "search_string": self.search_string}
        msg["df_display_args"] = self._with_highlight(session.df_display_args, self.search_string)
        try:
            self.write_message(json.dumps(msg))
        except Exception:
            log.debug("client state write failed for session=%s", self.session_id)

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
        # telemetry is wired for this session (#943), and bind the session's
        # telemetry sink (built once in /load_expr) for just this initial load —
        # genuine per-scroll row spans are deferred (v2).
        not_seen = not session._perf_first_payload_seen
        tele_sink = session.tele_sink if not_seen else None
        first_payload = not_seen and (perf_log.enabled() or tele_sink is not None)

        def _dispatch_and_send(pa, span_label):
            # Dispatch one window and send its two-frame reply: a JSON text
            # frame, then the binary Parquet frame when non-empty. On the initial
            # screen load each window is timed under its own span
            # (window_to_parquet encode + frame send); later per-scroll requests
            # run uninstrumented (first_payload False → nullcontext), deferred to
            # v2.
            span = (perf_log.perf_span(span_label, session=self.session_id)
                    if first_payload else nullcontext())
            with span:
                resp, parquet = _dispatch(pa)
                self.write_message(json.dumps(resp))
                if parquet:
                    self.write_message(parquet, binary=True)

        try:
            with perf_log.telemetry_context(self.session_id, tele_sink):
                _dispatch_and_send(payload_args, "firstpull.ws_first_payload")
                if first_payload:
                    session._perf_first_payload_seen = True
                # Eager second window (#896): its own span, not work riding inside
                # the first pull's context where it would surface only as an
                # unlabeled nested window_to_parquet record.
                second_pa = payload_args.get("second_request")
                if second_pa:
                    _dispatch_and_send(second_pa, "firstpull.ws_second_payload")
        except Exception:
            tb = traceback.format_exc()
            log.error("infinite_request error session=%s: %s", self.session_id, tb)
            self.write_message(json.dumps({"type": "infinite_resp", "key": payload_args, "length": 0,
                "error_info": tb if _BUCKAROO_DEBUG else "Request failed"}))

    def on_close(self):
        sessions = self.application.settings["sessions"]
        sessions.remove_ws_client(self.session_id, self)
