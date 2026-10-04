"""Server side of the stats wire protocol (rows-first s3 and s5).

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

A session also carries the policy resolved at load (``stats_policy.py``). A
target the server chose below ``full`` (a size rule, or the ceiling on a host
that asked for ``auto`` or ``full``) is applied only for a client that
advertised ``?caps=stats_update,stats_ondemand``: it gets the schema tier,
``df_meta.stats.status == "not_computed"`` and the policy fields. A client with
``stats_update`` only is told the session is ``pending`` and pulls the stats as
above, and one with no caps gets them synchronously, as for any deferred
session. A tier the host named below ``full`` (``scalar``, ``schema``) is its
choice and reaches every client as ``not_computed``. ``stats_to_pull`` decides,
per client, whether a session has stats left to compute.

A target of ``scalar`` (``serves_scalar_tier``) can be pulled by the client that
advertised both bits: its ``stats_request`` runs the units of a scalar ``StatRun``
and is answered with ``stats_update`` messages whose tier is ``scalar``. Nothing
is assigned. The run's fragments go to the clients that ask, as a filtered run's
would, and the dataflow, the session snapshot, ``summary_stats_cache`` and the
status stay as they were, so the scalar stats are never served as the complete
ones. Only the full run over every column reaches the final assignment
(``StatRun.assigns``).

That client can also say what it wants (rows-first p36a). ``stats_request`` takes
``tier`` (``scalar`` or ``full``), ``force`` and, with a ``tier``, ``columns`` that
scope the run to those columns (a run that is never assigned, like the scalar one).
The server judges every such request itself, in this order: a tier the ceiling
refuses for the cells asked for is answered ``stats_update {final: true, status:
"not_computed", reason: "ceiling"}`` and runs nothing; a whole-table tier below the
target, or above it without ``force``, is ``not_requestable``; while the cost guard
has paused the session, a request without ``force`` is answered with reason
``cost``. A ``force`` above the target sets the session's ``stats_override``
(``session.effective_stats_policy``) and clears the pause. An automatic request,
one without ``force``, that ran a unit over ``STATS_COST_BUDGET_S`` and left units
to run pauses the session (``cost_paused``): the status is ``not_computed`` for
``cost`` until a ``force`` request. The fields mean nothing to any other client,
or on a session with no policy. The demand scan (``stats_policy.demand_columns``)
names the columns the display config's ``color_map`` rules read, and
``df_meta.stats.demand_columns`` carries them to a client, which asks for them as
a scoped scalar request.

Every send site goes through ``build_state_message_for`` (or ``broadcast_state``,
which calls it per client), because the session holds one shared snapshot and
the client is known only to the handler that owns the connection.

A ``stats_request`` takes one of two shapes. Without ``incremental`` it is the
whole run: one synchronous call that runs every unit still to run, applies the
final assignment and answers with the complete ``all_stats``. With
``incremental: true`` it runs the units of the session's ``StatRun`` for about
``STATS_BUDGET_S`` (at least one, so a cold unit is the only one of its
request) and answers with the fragments this client has not seen. The request
that runs the last unit applies the final assignment (``complete_stats``): the
full-tier cache entry, ``summary_sd``, the session snapshot and the status,
in one step. A client that follows the run reads the same list through its own
cursor, so work is done once whoever asks.
"""
import copy
import dataclasses
import hashlib
import json
import logging
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

from buckaroo.dataflow.sd_cache import split_chain_by_scope
from buckaroo.df_util import old_col_new_col
from buckaroo.pluggable_analysis_framework import perf_log
from buckaroo.pluggable_analysis_framework.stat_units import Fragment
from buckaroo.server.data_loading import get_buckaroo_display_state
from buckaroo.server.session import (
    SessionState, build_state_message, effective_stats_policy, restore_stats_status, session_dataflow,
    stats_deferred_by_policy)
from buckaroo.server.stat_run import StatCursor, StatRun, stat_run_key
from buckaroo.server.stats_policy import TIERS, demand_columns, resolve_stats_policy

log = logging.getLogger("buckaroo.server.stats_wire")

# The capability a client advertises, as one of the comma-separated values of
# ``?caps=`` on the WebSocket URL: it merges ``stats_update`` messages. The
# connection is the only place it can be recorded, because ``open()`` sends the
# first message before the client has said anything.
STATS_UPDATE_CAP = "stats_update"

# The second capability bit: the client also renders ``not_computed``, honours
# ``auto_request`` and sends ``tier`` and ``force`` on ``stats_request``. It counts
# only together with ``stats_update``, which it builds on.
STATS_ONDEMAND_CAP = "stats_ondemand"

# The scopes a ``stats_request`` can name. ``raw`` is the unfiltered table of
# the session's current generation; filtered stats exist only through a
# dataflow-field change (``quick_command_args.search``), which bumps the
# generation.
STATS_SCOPES = ("raw",)

# The time an incremental ``stats_request`` may spend running units, in
# seconds. A request always runs one unit and stops starting new ones once this
# is spent, so a snapshot-cache hit (milliseconds) shares its request with the
# others and a query is alone in its own. It cannot cut a unit short: the
# longest unit is what a waiting ``infinite_request`` stalls behind.
STATS_BUDGET_S = 0.075

# The longest an automatic unit may take before the cost guard pauses the
# session, in seconds. PROVISIONAL: a unit cannot be cut short, so this bounds
# how long the loop is held by one unit that nobody asked for. The number is the
# tallyman client's base timeout (10 s), not a measurement of units. For scale:
# the largest unit on parking_2017 (10.8M rows x 43 columns), the scalar batch,
# takes 0.9 to 1.0 s, and the slowest in-limit telemetry load (an 11.8M-row CSV
# union) took 22 s for all of its units together.
STATS_COST_BUDGET_S = 10.0

# The tiers a ``stats_request`` can name. ``schema`` is what a session has until
# something is computed, so there is nothing to request at it.
REQUEST_TIERS = ("scalar", "full")


def parse_caps(raw: str) -> frozenset:
    """The capabilities in a ``?caps=a,b`` value."""
    return frozenset(cap for cap in (part.strip() for part in raw.split(",")) if cap)


def client_has_cap(client: Any, cap: str) -> bool:
    """Whether a WebSocket handler recorded ``cap`` at open. Anything else with
    no ``caps`` (a test double, a future non-WebSocket client) has none."""
    return cap in getattr(client, "caps", ())


def client_has_ondemand(client: Any) -> bool:
    """Whether a WebSocket handler advertised ``stats_update`` and
    ``stats_ondemand``, so a session the server put below ``full`` is applied
    for it as such."""
    return client_has_cap(client, STATS_UPDATE_CAP) and client_has_cap(client, STATS_ONDEMAND_CAP)


def stats_to_pull(session: SessionState, client: Any) -> bool:
    """Whether the session has stats left to compute from this client's side: it
    is ``pending``, or the server put it below ``full`` and the client cannot
    take that (``stats_deferred_by_policy``). A client with ``stats_update``
    pulls them with ``stats_request``, one with no caps gets them at connect."""
    return session.stats_status == "pending" or (stats_deferred_by_policy(session) and not client_has_ondemand(client))


def serves_scalar_tier(session: SessionState, client: Any) -> bool:
    """Whether a ``stats_request`` from ``client`` is answered with the scalar
    tier: the client advertised both bits, so it takes tiers, and the session has
    nothing computed (``not_computed``) and a policy target of ``scalar``,
    whether the size rule, the host or the ceiling put it there, or a forced
    request raised it (``effective_stats_policy``). Any other client of such a
    session is served as ``stats_to_pull`` says."""
    policy = effective_stats_policy(session)
    return (client_has_ondemand(client) and session.stats_status == "not_computed" and policy is not None
        and policy["tier_target"] == "scalar")


def resolve_session_policy(stats_tier: str, dataflow_tier: str, rows: int, cols: int) -> Optional[dict]:
    """The policy for a session the handler has just built: ``stats_tier`` is the
    host's request, ``dataflow_tier`` the tier its dataflow was built at, and
    ``rows`` and ``cols`` the size load already took (the cached count, so no
    query runs). ``None`` when the dataflow ran its stats in the constructor
    (``full``): there is nothing left to defer or refuse."""
    if dataflow_tier != "schema":
        return None
    return resolve_stats_policy("xorq", "xorq_build", rows, cols, host_tier=stats_tier)


def refresh_session_snapshot(session: SessionState, dataflow: Any) -> None:
    """Copy the dataflow's display state onto the session snapshot that new
    clients and every push read, and re-apply ``component_config`` so theme
    settings survive. The dataflow reaches no client until this runs. The demand
    columns follow the config the snapshot now holds."""
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
    refresh_demand_columns(session, dataflow)


def refresh_demand_columns(session: SessionState, dataflow: Any) -> None:
    """Put the columns the session's display config wants min and max for in
    ``session.stats_policy["demand_columns"]``, where ``df_meta.stats`` reports
    them: the demand scan (``stats_policy.demand_columns``) over the snapshot's
    config, read from the config alone with no query. Only a ``schema`` target
    has demand, since a higher one computes those columns anyway. The key is
    absent when there are none."""
    policy = session.stats_policy
    if policy is None:
        return
    columns: list = []
    if policy["tier_target"] == "schema" and dataflow.processed_df is not None:
        columns = demand_columns(session.df_display_args, old_col_new_col(dataflow.processed_df))
    if columns:
        policy["demand_columns"] = columns
    else:
        policy.pop("demand_columns", None)


def start_stat_run(session: SessionState, scope: str = "raw", tier: str = "full",
        columns: Optional[Sequence[Any]] = None) -> Optional[StatRun]:
    """The ``StatRun`` of the session's current generation for ``scope``, ``tier``
    and column group: the one it holds, or a new one planned from the dataflow
    and stored on the session under ``stat_run_key``. Planning sends no query.
    The run analyzes the frame ``assign_full_stats`` does, so running every unit
    of the full run gives the stats that call computes whole. A run at another
    tier, or over a column group (``columns``, original names), is never
    assigned (``StatRun.assigns``). ``None`` when there is no dataflow to plan
    from or the scope is not one a request can name."""
    dataflow = session_dataflow(session)
    if dataflow is None or dataflow.processed_df is None or scope not in STATS_SCOPES:
        return None
    key = stat_run_key(session.stats_gen, scope, tier, columns)
    run = session.stat_runs.get(key)
    if run is None:
        stats = dataflow.build_stats(dataflow.processed_df, run=False)
        state = dataclasses.replace(stats.state, tier=tier, columns=None if columns is None else tuple(columns))
        run = StatRun(session.stats_gen, scope, stats, state)
        session.stat_runs[key] = run
    return run


def display_args_hash(display_args: Any) -> str:
    """A digest of a ``df_display_args`` value, equal for equal content whatever
    the key order. JSON, because that is how the value reaches a client, and it
    reads a NaN the same each time."""
    return hashlib.sha1(json.dumps(display_args, sort_keys=True, default=str).encode()).hexdigest()


def highlighted_display_args(display_args: dict, term: str) -> dict:
    """A copy of ``df_display_args`` with ``term`` set as the highlight phrase
    of every string column's displayer, or with the highlight removed when the
    term is empty (#851). A copy, so the shared session snapshot is never
    changed."""
    overlay = copy.deepcopy(display_args)
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
    return overlay


def run_units(run: StatRun, budget_s: Optional[float], prefer: Sequence[str] = (),
        clock: Callable[[], float] = time.perf_counter, session_id: Optional[str] = None,
        timings: Optional[list] = None) -> int:
    """Run units of ``run`` for one request, and return how many.

    At least one runs while the run is pending. Another starts only while the
    time spent is under ``budget_s``, so units that cost milliseconds (their
    queries are snapshot-cache hits) run together and one that is a query ends
    its request. ``budget_s=None`` runs every unit still to run. ``prefer`` are
    column names as a client writes them (the rewritten ``a, b, c``), whose
    units go first. A unit that raises fails the run and the exception
    propagates. Each unit is a ``stats.unit`` span. ``timings``, when given,
    gets the seconds each unit took (the run's own timer), for the cost guard."""
    started = clock()
    ran = 0
    while run.status == "pending":
        if ran and budget_s is not None and clock() - started >= budget_s:
            break
        unit = run.next_unit(prefer, "rewritten")
        if unit is None:
            run.run_next()  # no unit is left: this marks the run complete
            break
        spent = run.elapsed_s
        with perf_log.perf_span("stats.unit", session=session_id, stats_gen=run.stats_gen, unit=unit.id,
            phase=unit.phase, cost=unit.cost, columns=len(unit.columns)):
            run.run_next(prefer, "rewritten")
        if timings is not None:
            timings.append(run.elapsed_s - spent)
        ran += 1
    return ran


def partial_payload(dataflow: Any, run: StatRun, fragments: Sequence[Fragment]) -> Any:
    """The ``all_stats`` payload (an inline wide ``DFEnvelope``) of the columns
    ``fragments`` cover: their stats so far, assembled as ``merged_sd`` is, so
    ``init_sd``, a processing step's sd and the ``cleaned_*`` and ``filtered_*``
    layers apply as they will in the complete state. A client merges it into
    its ``all_stats`` key by key, so a stat sent again with a later fragment
    only replaces itself."""
    rewritten = dict(old_col_new_col(run.acc.state.data))
    touched = {rewritten[col] for fragment in fragments for col in fragment if col in rewritten}
    merged = dataflow._assemble_merged_sd(run.raw_sd())
    return dataflow._sd_to_jsondf({col: stats for col, stats in merged.items() if col in touched})


def _full_stats_key(dataflow: Any) -> Any:
    """The ``summary_stats_cache`` key of the current state's full-tier sd."""
    return dataflow._scope_cache_key(split_chain_by_scope(dataflow.operations)["filt"], tier="full")


def _cached_full_sd(dataflow: Any) -> Any:
    """The full-tier sd of the current state if an earlier visit to it left one."""
    return dataflow.summary_stats_cache.get(_full_stats_key(dataflow))


def assign_full_stats(dataflow: Any, computed: Optional[tuple] = None) -> None:
    """Take a schema-tier dataflow to the full tier: use the current state's
    full stats (found in ``summary_stats_cache``, where an earlier visit to the
    same state left them, or ``computed``, the ``(sd, errs)`` of a finished
    ``StatRun``, or computed here whole), write them under the full-tier key,
    then assign ``summary_sd``. Assigning runs the cascade, which fills the
    other scopes' entries it still lacks and rebuilds ``merged_sd``,
    ``df_data_dict`` and ``df_display_args``.

    The cache entry goes in first because ``_populate_sd_cache`` skips a key it
    finds, so the filt scope is not computed a second time. The tier is a
    plain attribute, flipped before the compute so ``_get_summary_sd`` runs the
    full pipeline, and put back if anything raises."""
    tier = dataflow.stats_tier
    key = _full_stats_key(dataflow)
    dataflow.stats_tier = "full"
    try:
        sd = dataflow.summary_stats_cache.get(key)
        errs = {}
        if sd is None:
            sd, errs = computed if computed is not None else dataflow._get_summary_sd(dataflow.processed_df)
            dataflow.summary_stats_cache = {**dataflow.summary_stats_cache, key: sd}
        dataflow.summary_sd = sd
        dataflow.errs = errs
    except Exception:
        dataflow.stats_tier = tier
        raise


def _run_summary(dataflow: Any, run: StatRun) -> tuple:
    """The ``(sd, errs)`` of a finished run, as ``_get_summary_sd`` returns them
    (it raises on a failed stat in debug mode, and so does this). Only a run that
    assigns has them: a scalar or column-scoped run is a part of the stats, and
    caching it as the whole would serve it as complete."""
    if not run.assigns:
        raise ValueError(f"a {run.tier} run over {'every column' if run.state.columns is None else 'some columns'} "
            "is not the session's stats and cannot be assigned")
    errs = run.errs()
    if errs and dataflow.debug:
        raise Exception("Error executing analysis")
    return run.raw_sd(), errs


def _run_span_attrs(run: StatRun) -> dict:
    """What the completion span says about a run that spanned requests: the
    units it took and their summed time, and for a backend with a snapshot
    cache (xorq) the outcome ``firstpull.summary_stats`` carries for a whole
    run (#943)."""
    attrs: Dict[str, Any] = {"units": len(run.units), "run_secs": round(run.elapsed_s, 4)}
    cache_run_stats = getattr(run.stats, "cache_run_stats", None)
    if cache_run_stats is not None:
        cs = cache_run_stats()
        attrs.update(cache_status=cs["status"], cache_hits=cs["hits"], cache_misses=cs["misses"],
            cache_secs=attrs["run_secs"], cache_snapshots=cs["snapshots"], cache_bytes=cs["bytes"],
            cache_write_errors=cs["write_errors"])
    return attrs


def _fail_stats(session: SessionState) -> None:
    """A stats run failed: that is the session's state for this generation, so
    no request retries it and the next generation starts clean."""
    session.stats_status, session.stats_reason = "error", "stats_failed"
    session.stat_runs.clear()


def complete_stats(session: SessionState) -> bool:
    """Run the stats a pending session is missing (or one the server put below
    ``full``, for a client that cannot take that) and publish them: the final
    assignment (``assign_full_stats``), then the session snapshot refreshed and
    the status set to ``complete`` in the same step, so ``all_stats`` and
    ``df_meta.stats`` cannot disagree. Returns whether the session is complete.

    When the generation has a ``StatRun``, its remaining units run (none if it
    is finished) and its results are what is assigned, so a unit that a client
    already ran is not run again. With no run the whole computation is one
    ``_get_summary_sd`` call, which runs the same units in the same order. The
    run is freed with the assignment.

    A failure is the session's state for this generation (``error``, reason
    ``stats_failed``) and is not retried by the next request; the next
    generation starts clean."""
    if session.stats_status == "complete":
        return True
    dataflow = session_dataflow(session)
    if not (session.stats_status == "pending" or stats_deferred_by_policy(session)) or dataflow is None:
        return False
    run_key = (session.stats_gen, "raw")
    with (
        perf_log.telemetry_context(session.session_id, session.tele_sink),
        perf_log.perf_span("firstpull.stats_total", session=session.session_id, stats_gen=session.stats_gen) as span,
    ):
        try:
            run = session.stat_runs.get(run_key)
            if run is not None and _cached_full_sd(dataflow) is None:
                run_units(run, None, session_id=session.session_id)
                span.set_attr(**_run_span_attrs(run))
                assign_full_stats(dataflow, computed=_run_summary(dataflow, run))
            else:
                assign_full_stats(dataflow)
            refresh_session_snapshot(session, dataflow)
        except Exception:
            log.error("stats run failed session=%s stats_gen=%s: %s", session.session_id, session.stats_gen,
                traceback.format_exc())
            _fail_stats(session)
            return False
    session.stat_runs.pop(run_key, None)
    session.stats_status, session.stats_reason = "complete", None
    return True


def build_state_message_for(session: SessionState, client: Any, metadata: Optional[dict] = None) -> dict:
    """The ``initial_state`` message for one client.

    A client without the ``stats_update`` capability on a deferred session that
    has stats to compute for it (``stats_to_pull``) gets them run first, so its
    message is complete; a capable client gets the session snapshot as it is
    (stats-free while the stats are to be pulled) and pulls the rest. A client
    that also advertised ``stats_ondemand`` is told the session as the server
    resolved it (``not_computed`` with the policy fields); the others are told
    ``pending`` where the server chose a target below ``full``. The search term
    is the recipient's own (#851).

    A capable client is also told apart from the display config it holds: the
    digest of the one a pending frame carried is kept on it, so the final
    ``stats_update`` can say whether the config it would send differs."""
    if (session.stats_delivery == "deferred" and stats_to_pull(session, client)
            and not client_has_cap(client, STATS_UPDATE_CAP)):
        complete_stats(session)
    if client_has_cap(client, STATS_UPDATE_CAP):
        client.display_args_hash = (display_args_hash(session.df_display_args)
            if stats_to_pull(session, client) else None)
    return build_state_message(session, metadata=metadata, search_string=getattr(client, "search_string", ""),
        ondemand=client_has_ondemand(client))


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


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _plan_run(session: SessionState, tier: str = "full", columns: Optional[Sequence[Any]] = None) -> Optional[StatRun]:
    """The session's ``StatRun`` at ``tier`` (over ``columns``, original names,
    when a request scoped it) for the current generation, or ``None`` when it
    cannot be planned (there is no frame, or the dataflow's stats class cannot
    plan the one it has: a post-processor that failed leaves an error frame). For
    the full tier the whole-run path then decides what the stats are."""
    try:
        return start_stat_run(session, tier=tier, columns=columns)
    except Exception:
        log.warning("stat units not planned session=%s stats_gen=%s: %s", session.session_id, session.stats_gen,
            traceback.format_exc())
        return None


def _serve_units(session: SessionState, client: Any, prefer: Sequence[str], stats_gen: Any, scope: Any,
        started: float, info: dict) -> Optional[dict]:
    """The reply to an incremental request on a pending session, when the
    answer is the fragments this client has not seen: a partial ``stats_update``
    (``final`` false), or ``stats_aborted`` when a unit failed. ``None`` when
    the request is not answered that way: the stats are cached or cannot be
    planned (the whole-run path takes them), or the run is now finished and the
    caller publishes it.

    A client that is behind the run is caught up and no unit runs for it, so
    work is done once and a client that asks late reads it all from its own
    cursor."""
    dataflow = session_dataflow(session)
    if _cached_full_sd(dataflow) is not None:
        return None
    run = _plan_run(session)
    if run is None:
        return None
    cursor = getattr(client, "stats_cursor", None) or StatCursor()
    if cursor.caught_up(run):
        try:
            info["units"] = run_units(run, STATS_BUDGET_S, prefer, session_id=session.session_id,
                timings=info.setdefault("timings", []))
        except Exception:
            log.error("stat unit failed session=%s stats_gen=%s: %s", session.session_id, session.stats_gen,
                traceback.format_exc())
            _fail_stats(session)
            return _aborted(stats_gen, scope, "error", session)
    fragments = cursor.take(run)
    if run.status != "pending":
        return None
    return {"type": "stats_update", "stats_gen": stats_gen, "scope": scope, "tier": "full",
        "final": False, "remaining": run.remaining, "payload": partial_payload(dataflow, run, fragments),
        "elapsed_ms": _elapsed_ms(started)}


def _serve_run(session: SessionState, client: Any, prefer: Sequence[str], incremental: bool, stats_gen: Any,
        scope: Any, started: float, info: dict, tier: str = "scalar",
        columns: Optional[Sequence[Any]] = None) -> dict:
    """The reply to a ``stats_request`` served from a run that is not the
    session's stats: the ``scalar`` run over the whole table, or a run over named
    ``columns`` (original names) at ``tier``. A ``stats_update`` with that tier
    holding the fragments this client has not seen, ``final`` once the run is
    done; the final one also says what the session still is (``status``, and the
    ``reason``), since this run did not change it. An incremental request runs
    units for the time budget, as the full run's does; any other runs every unit
    still to run.

    Nothing is assigned. The run stays on the session for the generation, so a
    client that asks later is caught up from the fragments with no unit run, and
    the status, the snapshot and the caches are as they were. A unit that raises
    aborts the request and the run (it is not retried) but not the session, whose
    full tier is still open."""
    run = _plan_run(session, tier, columns)
    if run is None or run.status == "error":
        return _aborted(stats_gen, scope, "error", session)
    cursor = getattr(client, "stats_cursor", None) or StatCursor()
    if cursor.caught_up(run):
        try:
            info["units"] = run_units(run, STATS_BUDGET_S if incremental else None, prefer,
                session_id=session.session_id, timings=info.setdefault("timings", []))
        except Exception:
            log.error("%s stat unit failed session=%s stats_gen=%s: %s", run.tier, session.session_id,
                session.stats_gen, traceback.format_exc())
            return _aborted(stats_gen, scope, "error", session)
    fragments = cursor.take(run)
    reply = {"type": "stats_update", "stats_gen": stats_gen, "scope": scope, "tier": run.tier,
        "final": run.status != "pending", "remaining": run.remaining,
        "payload": partial_payload(session_dataflow(session), run, fragments), "elapsed_ms": _elapsed_ms(started)}
    if reply["final"]:
        reply["status"] = session.stats_status
        if session.stats_reason:
            reply["reason"] = session.stats_reason
    return reply


@dataclass(frozen=True)
class TierRequest:
    """The part of a ``stats_request`` an ondemand client's ``tier``, ``force``
    and ``columns`` say. ``tier`` is ``None`` for the session's own target;
    ``columns`` (original names, in frame order) is set only for a request that
    scopes the run, which needs a ``tier``."""
    tier: Optional[str]
    force: bool
    columns: Optional[tuple]


def tier_fields_apply(session: SessionState, client: Any) -> bool:
    """Whether ``tier``, ``force`` and a scoping ``columns`` mean anything for
    this request: the client advertised both bits, and the session has a policy
    to enforce them against. For any other client they are ignored."""
    return client_has_ondemand(client) and session.stats_policy is not None


def _tier_request(msg: dict, dataflow: Any) -> Optional[TierRequest]:
    """The request's ``TierRequest``, or ``None`` when a field is not one the
    server can read: a ``tier`` other than ``scalar`` or ``full``, a ``force``
    that is not a boolean, or ``columns`` (with a ``tier``) that is not a
    non-empty list of the grid's column names. Without a ``tier``, ``columns`` is
    only the hint it always was."""
    tier, force, columns = msg.get("tier"), msg.get("force"), msg.get("columns")
    force = False if force is None else force
    if (tier is not None and tier not in REQUEST_TIERS) or not isinstance(force, bool):
        return None
    if tier is None or columns is None:
        return TierRequest(tier, force, None)
    pairs = old_col_new_col(dataflow.processed_df)
    if not (isinstance(columns, list) and columns and all(isinstance(c, str) for c in columns)
            and set(columns) <= {rewritten for _orig, rewritten in pairs}):
        return None
    wanted = set(columns)
    return TierRequest(tier, force, tuple(orig for orig, rewritten in pairs if rewritten in wanted))


def _refused(session: SessionState, stats_gen: Any, scope: Any, tier: str, reason: str, started: float,
        info: dict) -> dict:
    """The reply to a request the server will not run (reason ``ceiling`` or
    ``cost``): a final ``stats_update`` with no payload that says the session has
    no more stats than it had, so a client can show why and stop asking."""
    info["refused"] = reason
    return {"type": "stats_update", "stats_gen": stats_gen, "scope": scope, "tier": tier, "final": True,
        "remaining": 0, "status": "not_computed", "reason": reason, "elapsed_ms": _elapsed_ms(started)}


def _gate_request(session: SessionState, asked: TierRequest, stats_gen: Any, scope: Any, started: float,
        info: dict) -> Optional[dict]:
    """Judge a tier request against the policy in force, in the order the module
    docstring gives: the ceiling for the cells asked for (``resolve_stats_policy``
    with the tier as the host's, the same function load uses), then, for a
    whole-table request, whether the tier is the target or above it with
    ``force``, then the cost pause. Returns the reply that refuses it, or
    ``None`` when it may run. The count is the one load took."""
    policy = effective_stats_policy(session)
    estimate, target = policy["estimate"], policy["tier_target"]
    scoped = asked.columns is not None
    tier = asked.tier or target
    if not scoped and tier == "schema":
        return _aborted(stats_gen, scope, "not_requestable", session)
    cols = len(asked.columns) if scoped else estimate["cols"]
    if resolve_stats_policy("xorq", "xorq_build", estimate["rows"], cols, host_tier=tier)["tier_target"] != tier:
        return _refused(session, stats_gen, scope, tier, "ceiling", started, info)
    if not scoped:
        rank, target_rank = TIERS.index(tier), TIERS.index(target)
        if rank < target_rank or (rank > target_rank and not asked.force):
            return _aborted(stats_gen, scope, "not_requestable", session)
    if session.cost_paused and not asked.force:
        return _refused(session, stats_gen, scope, tier, "cost", started, info)
    return None


def _apply_force(session: SessionState, client: Any, asked: TierRequest) -> None:
    """What a ``force`` request does to the session before it runs: clear the
    cost pause, and for a whole-table tier above the target, record the override
    so the target (and the status) follow it for this and later unfiltered
    generations. The client that forced a whole-table ``full`` run, whether it
    raised the target or continued a paused run to it, holds the schema-tier
    display config its ``not_computed`` frame carried (a frame that is not
    ``pending`` records no digest), so its digest is kept for the final reply to
    compare."""
    if not asked.force:
        return
    session.cost_paused = False
    target = effective_stats_policy(session)["tier_target"]
    tier = asked.tier or target
    whole_table = asked.columns is None
    if whole_table and TIERS.index(tier) > TIERS.index(target):
        session.stats_override, session.stats_override_gen = tier, session.stats_gen
    if whole_table and tier == "full" and getattr(client, "display_args_hash", None) is None:
        client.display_args_hash = display_args_hash(session.df_display_args)
    restore_stats_status(session)


def _pause_if_slow(session: SessionState, reply: dict, info: dict) -> None:
    """The cost guard. An automatic request (one with no ``force``, from a client
    the fields apply to) whose reply leaves units to run, and which ran a unit
    over ``STATS_COST_BUDGET_S``, pauses the session: the status is
    ``not_computed`` for ``cost``, and the next automatic request is refused until
    a ``force`` one clears it. A request that finished the run holds nothing back,
    and a forced one is the user's own choice."""
    if not info.get("automatic") or reply["type"] != "stats_update" or reply["final"]:
        return
    if max(info.get("timings") or [0.0]) > STATS_COST_BUDGET_S:
        session.cost_paused = True
        session.stats_status, session.stats_reason = "not_computed", "cost"
        info["paused"] = True


def _rebuilt_display_args(session: SessionState, client: Any) -> Optional[dict]:
    """The session's display config, when it differs from the one this client
    holds: the stats-derived parts of a config (a float column's ``minWidth``)
    change when the stats arrive. The client's own highlight is kept on it,
    since the config replaces the one that carries it. ``None`` when the client
    holds the current config, or there is no record of one to compare with."""
    held = getattr(client, "display_args_hash", None)
    if held is None:
        return None
    client.display_args_hash = None
    if display_args_hash(session.df_display_args) == held:
        return None
    term = getattr(client, "search_string", "")
    return highlighted_display_args(session.df_display_args, term) if term else session.df_display_args


def _answer_stats_request(session: Optional[SessionState], msg: dict, client: Any, started: float,
        info: dict) -> dict:
    stats_gen, scope = msg.get("stats_gen"), msg.get("scope", "raw")
    columns = msg.get("columns")
    prefer = [c for c in columns if isinstance(c, str)] if isinstance(columns, list) else []
    incremental = msg.get("incremental")
    dataflow = session_dataflow(session)
    if session is None or dataflow is None:
        return _aborted(stats_gen, scope, "no_data")
    if stats_gen != session.stats_gen:
        return _aborted(stats_gen, scope, "stale", session)
    if scope not in STATS_SCOPES:
        return _aborted(stats_gen, scope, "unsupported_scope", session)
    if incremental is not None and not isinstance(incremental, bool):
        return _aborted(stats_gen, scope, "bad_request", session)
    if tier_fields_apply(session, client):
        asked = _tier_request(msg, dataflow)
        if asked is None:
            return _aborted(stats_gen, scope, "bad_request", session)
        # A complete session answers from the dataflow, and a failed one is an
        # error below, whatever the request names.
        if session.stats_status in ("pending", "not_computed"):
            refusal = _gate_request(session, asked, stats_gen, scope, started, info)
            if refusal is not None:
                return refusal
            info["automatic"] = not asked.force
            _apply_force(session, client, asked)
            if asked.columns is not None:
                return _serve_run(session, client, prefer, bool(incremental), stats_gen, scope, started, info,
                    tier=asked.tier, columns=asked.columns)
    if serves_scalar_tier(session, client):
        return _serve_run(session, client, prefer, bool(incremental), stats_gen, scope, started, info)
    to_pull = stats_to_pull(session, client)
    if session.stats_status == "not_computed" and not to_pull:
        return _aborted(stats_gen, scope, "not_requestable", session)
    if to_pull and incremental:
        reply = _serve_units(session, client, prefer, stats_gen, scope, started, info)
        if reply is not None:
            return reply
    if to_pull:
        complete_stats(session)
    if session.stats_status != "complete":
        return _aborted(stats_gen, scope, "error", session)
    # Complete: from here the answer is the dataflow's own all_stats, with no
    # query, whether this request ran the stats or an earlier one did.
    reply = {"type": "stats_update", "stats_gen": stats_gen, "scope": scope, "tier": dataflow.stats_tier,
        "final": True, "remaining": 0, "payload": session.df_data_dict["all_stats"],
        "elapsed_ms": _elapsed_ms(started)}
    display_args = _rebuilt_display_args(session, client)
    if display_args is not None:
        reply["df_display_args"] = display_args
    return reply


def handle_stats_request(session: Optional[SessionState], msg: dict, client: Any = None) -> dict:
    """Answer a ``stats_request {stats_gen, scope, columns?, incremental?}``: a
    ``stats_update`` or a ``stats_aborted``. ``client`` is the handler that
    received it, which holds the connection's cursor into the run and the
    display config it was last sent.

    Without ``incremental`` the request is the whole run: every unit still to
    run, then a ``stats_update`` that is ``final`` and carries the complete
    ``all_stats`` as an inline wide ``DFEnvelope`` (self-contained, so binary
    pairing stays single-slot). With ``incremental: true`` it is a time-boxed
    step (see ``_serve_units``): a ``stats_update`` with ``final`` false
    carries the stats of the columns this client has not seen, ``remaining``
    counts the units left, and the reply that follows the last unit is the
    ``final`` one, with the complete ``all_stats`` and, when the stats changed
    it, the rebuilt ``df_display_args``. ``columns`` are the grid's column
    names (``a, b, c``), a hint for which units go first, and a whole-run
    request ignores it. A malformed request is ``stats_aborted`` with reason
    ``bad_request``, and is not run as a whole run. On a session whose target is
    ``scalar`` an ondemand client's request is answered as ``_serve_run``
    says: ``stats_update`` messages with ``tier: "scalar"`` and nothing assigned.
    ``tier``, ``force`` and ``columns`` are read for an ondemand client of a
    session with a policy (see the module docstring), and ``elapsed_ms`` is in
    every ``stats_update``.

    The ``stats.request`` span records the request and its ``outcome``
    (``update`` or the abort reason), which is where updates sent, requests
    dropped as stale and errors are counted. The caller binds the session's
    telemetry sink around this call."""
    stats_gen, scope, columns = msg.get("stats_gen"), msg.get("scope", "raw"), msg.get("columns")
    started = time.perf_counter()
    info: dict = {}
    with perf_log.perf_span("stats.request", session=session.session_id if session else None, stats_gen=stats_gen,
        scope=scope, columns=len(columns) if isinstance(columns, list) else None) as span:
        try:
            reply = _answer_stats_request(session, msg, client, started, info)
        except Exception:
            log.error("stats_request error session=%s: %s", session.session_id if session else None,
                traceback.format_exc())
            reply = _aborted(stats_gen, scope, "error", session)
        _pause_if_slow(session, reply, info)
        if reply["type"] == "stats_update":
            span.set_attr(outcome="update", tier=reply["tier"], final=reply["final"], remaining=reply["remaining"])
        else:
            span.set_attr(outcome=reply["reason"])
        if "units" in info:
            span.set_attr(units=info["units"])
        if "refused" in info:
            span.set_attr(refused=info["refused"])
        if info.get("paused"):
            span.set_attr(paused=True)
    return reply
