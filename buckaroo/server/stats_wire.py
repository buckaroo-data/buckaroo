"""Server side of the stats wire protocol (rows-first s3).

A deferred session (``stats_delivery="deferred"``) publishes its dataflow at the
schema tier and leaves the rest of the stats to later. Two kinds of client
reach them:

* A client that advertised ``?caps=stats_update`` on its WebSocket URL gets a
  stats-free ``initial_state`` (``df_meta.stats.status == "pending"``), pulls
  the stats with ``stats_request {stats_gen, scope}`` and merges the
  ``stats_update`` that answers it. A request for a generation the session has
  left gets ``stats_aborted``.
* Any other client gets complete messages: ``build_state_message_for`` runs the
  missing stats synchronously before it builds a message for one, which is
  today's cost, paid on the loop.

Every send site goes through ``build_state_message_for`` (or ``broadcast_state``,
which calls it per client), because the session holds one shared snapshot and
the client is known only to the handler that owns the connection.

The request here is the whole run: one synchronous call that computes the full
stats and applies the final assignment (``assign_full_stats``,
``refresh_session_snapshot``). Resumable units generalize it later.
"""
import json
import logging
import time
import traceback
from typing import Any, Optional

from buckaroo.dataflow.sd_cache import split_chain_by_scope
from buckaroo.pluggable_analysis_framework import perf_log
from buckaroo.server.data_loading import get_buckaroo_display_state
from buckaroo.server.session import SessionState, build_state_message
from buckaroo.server.stat_run import StatRun

log = logging.getLogger("buckaroo.server.stats_wire")

# The capability a client advertises, as one of the comma-separated values of
# ``?caps=`` on the WebSocket URL: it merges ``stats_update`` messages. The
# connection is the only place it can be recorded, because ``open()`` sends the
# first message before the client has said anything.
STATS_UPDATE_CAP = "stats_update"

# The scopes a ``stats_request`` can name. ``raw`` is the unfiltered table of
# the session's current generation; filtered stats exist only through a
# dataflow-field change (``quick_command_args.search``), which bumps the
# generation.
STATS_SCOPES = ("raw",)


def parse_caps(raw: str) -> frozenset:
    """The capabilities in a ``?caps=a,b`` value."""
    return frozenset(cap for cap in (part.strip() for part in raw.split(",")) if cap)


def client_has_cap(client: Any, cap: str) -> bool:
    """Whether a WebSocket handler recorded ``cap`` at open. Anything else with
    no ``caps`` (a test double, a future non-WebSocket client) has none."""
    return cap in getattr(client, "caps", ())


def session_dataflow(session: Optional[SessionState]) -> Any:
    """The dataflow behind a buckaroo-mode session, or ``None`` (viewer and lazy
    sessions have none)."""
    if session is None or session.mode != "buckaroo":
        return None
    return session.xorq_dataflow if session.backend == "xorq" else session.dataflow


def refresh_session_snapshot(session: SessionState, dataflow: Any) -> None:
    """Copy the dataflow's display state onto the session snapshot that new
    clients and every push read, and re-apply ``component_config`` so theme
    settings survive. The dataflow reaches no client until this runs."""
    refreshed = get_buckaroo_display_state(dataflow)
    session.df_display_args = refreshed["df_display_args"]
    session.df_data_dict = refreshed["df_data_dict"]
    session.df_meta = refreshed["df_meta"]
    session.buckaroo_options = refreshed["buckaroo_options"]
    session.command_config = refreshed["command_config"]
    if session.component_config and session.df_display_args:
        for key in session.df_display_args:
            dvc = session.df_display_args[key].get("df_viewer_config")
            if dvc is not None:
                dvc["component_config"] = {**dvc.get("component_config", {}), **session.component_config}


def start_stat_run(session: SessionState, scope: str = "raw") -> Optional[StatRun]:
    """The ``StatRun`` of the session's current generation for ``scope``: the one
    it holds, or a new one planned from the dataflow and stored on the session.
    Planning sends no query. The run analyzes the frame ``assign_full_stats``
    does, so running every unit gives the stats that call computes whole.
    ``None`` when there is no dataflow to plan from or the scope is not one a
    request can name."""
    dataflow = session_dataflow(session)
    if dataflow is None or dataflow.processed_df is None or scope not in STATS_SCOPES:
        return None
    key = (session.stats_gen, scope)
    run = session.stat_runs.get(key)
    if run is None:
        run = StatRun(session.stats_gen, scope, dataflow.build_stats(dataflow.processed_df, run=False))
        session.stat_runs[key] = run
    return run


def assign_full_stats(dataflow: Any) -> None:
    """Take a schema-tier dataflow to the full tier: compute the current
    state's full stats (or find them in ``summary_stats_cache``, where an
    earlier visit to the same state left them), write them under the full-tier
    key, then assign ``summary_sd``. Assigning runs the cascade, which fills the
    other scopes' entries it still lacks and rebuilds ``merged_sd``,
    ``df_data_dict`` and ``df_display_args``.

    The cache entry goes in first because ``_populate_sd_cache`` skips a key it
    finds, so the filt scope is not computed a second time. The tier is a
    plain attribute, flipped before the compute so ``_get_summary_sd`` runs the
    full pipeline, and put back if anything raises."""
    tier = dataflow.stats_tier
    filt_chain = split_chain_by_scope(dataflow.operations)["filt"]
    key = dataflow._scope_cache_key(filt_chain, tier="full")
    dataflow.stats_tier = "full"
    try:
        sd = dataflow.summary_stats_cache.get(key)
        errs = {}
        if sd is None:
            sd, errs = dataflow._get_summary_sd(dataflow.processed_df)
            dataflow.summary_stats_cache = {**dataflow.summary_stats_cache, key: sd}
        dataflow.summary_sd = sd
        dataflow.errs = errs
    except Exception:
        dataflow.stats_tier = tier
        raise


def complete_stats(session: SessionState) -> bool:
    """Run the stats a pending session is missing, in one synchronous call, and
    publish them: the final assignment (``assign_full_stats``), then the session
    snapshot refreshed and the status set to ``complete`` in the same step, so
    ``all_stats`` and ``df_meta.stats`` cannot disagree. Returns whether the
    session is complete.

    A failure is the session's state for this generation (``error``, reason
    ``stats_failed``) and is not retried by the next request; the next
    generation starts clean."""
    if session.stats_status == "complete":
        return True
    dataflow = session_dataflow(session)
    if session.stats_status != "pending" or dataflow is None:
        return False
    with (
        perf_log.telemetry_context(session.session_id, session.tele_sink),
        perf_log.perf_span("firstpull.stats_total", session=session.session_id, stats_gen=session.stats_gen),
    ):
        try:
            assign_full_stats(dataflow)
            refresh_session_snapshot(session, dataflow)
        except Exception:
            log.error("stats run failed session=%s stats_gen=%s: %s", session.session_id, session.stats_gen,
                traceback.format_exc())
            session.stats_status, session.stats_reason = "error", "stats_failed"
            return False
    session.stats_status, session.stats_reason = "complete", None
    return True


def build_state_message_for(session: SessionState, client: Any, metadata: Optional[dict] = None) -> dict:
    """The ``initial_state`` message for one client.

    A client without the ``stats_update`` capability on a pending deferred
    session gets its missing stats run first, so its message is complete; a
    capable client gets the session snapshot as it is (stats-free while the
    session is pending) and pulls the rest. The search term is the recipient's
    own (#851)."""
    if (session.stats_delivery == "deferred" and session.stats_status == "pending"
            and not client_has_cap(client, STATS_UPDATE_CAP)):
        complete_stats(session)
    return build_state_message(session, metadata=metadata, search_string=getattr(client, "search_string", ""))


def broadcast_state(session: SessionState, metadata: Optional[dict] = None, reset_search: bool = False) -> None:
    """Send every connected client its own ``initial_state``. A client whose
    write fails is dropped from the session.

    ``reset_search`` clears each client's live search term first (#851), for a
    push that replaces the dataset. Clients that merge ``stats_update`` go
    first: a legacy client's message completes the session's stats, and a
    message built after that would carry them, so the capable client would
    never see the pending state its own frame is meant to describe."""
    for client in sorted(session.ws_clients, key=lambda c: not client_has_cap(c, STATS_UPDATE_CAP)):
        try:
            if reset_search:
                client.search_string = ""
            client.write_message(json.dumps(build_state_message_for(session, client, metadata=metadata)))
        except Exception:
            session.ws_clients.discard(client)


def _aborted(stats_gen: Any, scope: Any, reason: str, session: Optional[SessionState] = None) -> dict:
    """``stats_aborted``: the request was not run. ``stats_gen`` echoes the
    request so the client can pair them; ``current_gen`` is the session's, so a
    stale client can ask again without waiting for the next ``initial_state``."""
    msg: dict = {"type": "stats_aborted", "stats_gen": stats_gen, "scope": scope, "reason": reason}
    if session is not None:
        msg["current_gen"] = session.stats_gen
    return msg


def _answer_stats_request(session: Optional[SessionState], stats_gen: Any, scope: Any, started: float) -> dict:
    dataflow = session_dataflow(session)
    if session is None or dataflow is None:
        return _aborted(stats_gen, scope, "no_data")
    if stats_gen != session.stats_gen:
        return _aborted(stats_gen, scope, "stale", session)
    if scope not in STATS_SCOPES:
        return _aborted(stats_gen, scope, "unsupported_scope", session)
    if session.stats_status == "not_computed":
        return _aborted(stats_gen, scope, "not_requestable", session)
    if session.stats_status == "error" or (session.stats_status == "pending" and not complete_stats(session)):
        return _aborted(stats_gen, scope, "error", session)
    # Complete: from here the answer is the dataflow's own all_stats, with no
    # query, whether this request ran the stats or an earlier one did.
    return {"type": "stats_update", "stats_gen": stats_gen, "scope": scope, "tier": dataflow.stats_tier,
        "final": True, "payload": session.df_data_dict["all_stats"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}


def handle_stats_request(session: Optional[SessionState], msg: dict) -> dict:
    """Answer a ``stats_request {stats_gen, scope, columns?}``: a
    ``stats_update`` carrying the complete ``all_stats`` as an inline wide
    ``DFEnvelope`` (self-contained, so binary pairing stays single-slot), or a
    ``stats_aborted``. ``columns`` is a hint a whole-run request ignores.

    The ``stats.request`` span records the request and its ``outcome``
    (``update`` or the abort reason), which is where updates sent, requests
    dropped as stale and errors are counted. The caller binds the session's
    telemetry sink around this call."""
    stats_gen, scope, columns = msg.get("stats_gen"), msg.get("scope", "raw"), msg.get("columns")
    started = time.perf_counter()
    with perf_log.perf_span("stats.request", session=session.session_id if session else None, stats_gen=stats_gen,
        scope=scope, columns=len(columns) if isinstance(columns, list) else None) as span:
        try:
            reply = _answer_stats_request(session, stats_gen, scope, started)
        except Exception:
            log.error("stats_request error session=%s: %s", session.session_id if session else None,
                traceback.format_exc())
            reply = _aborted(stats_gen, scope, "error", session)
        if reply["type"] == "stats_update":
            span.set_attr(outcome="update", tier=reply["tier"])
        else:
            span.set_attr(outcome=reply["reason"])
    return reply
