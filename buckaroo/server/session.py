import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import pandas as pd
# polars is optional — only used in lazy mode

log = logging.getLogger("buckaroo.server.session")

_DEFAULT_SESSION_TTL_S = 3600.0      # 1 hour idle before eviction
_DEFAULT_EVICTION_INTERVAL_S = 300.0  # check every 5 minutes

# How a session reaches its stats tier: ``inline`` computes them in the
# dataflow constructor (today's behaviour); ``deferred`` builds the schema tier
# first and leaves the rest to later requests.
STATS_DELIVERIES = ("inline", "deferred")
# The policy of a session no /load_expr has set one for.
DEFAULT_STATS_TIER = "full"
DEFAULT_STATS_DELIVERY = "inline"


def dataflow_stats_tier(stats_tier: str, stats_delivery: str) -> str:
    """The tier a session's dataflow is constructed at. A deferred session
    starts at the schema tier whatever tier it is headed for."""
    return "schema" if stats_delivery == "deferred" else stats_tier


def initial_stats_status(stats_tier: str, stats_delivery: str) -> tuple[str, Optional[str]]:
    """The status, and its reason, of a session whose stats generation has just
    started, from the policy pair alone."""
    if stats_tier != "full":
        return "not_computed", "host"
    if stats_delivery == "deferred":
        return "pending", None
    return "complete", None


@dataclass
class SessionState:
    session_id: str
    path: str
    df: Optional[pd.DataFrame] = None
    metadata: dict = field(default_factory=dict)
    ws_clients: set = field(default_factory=set)
    df_display_args: dict = field(default_factory=dict)
    df_data_dict: dict = field(default_factory=dict)
    df_meta: dict = field(default_factory=dict)
    # Lazy polars mode fields
    ldf: Optional[Any] = None  # polars LazyFrame (mode="lazy")
    orig_to_rw: dict = field(default_factory=dict)
    rw_to_orig: dict = field(default_factory=dict)
    # Buckaroo mode fields
    mode: str = "viewer"  # "viewer", "buckaroo", or "lazy"
    backend: str = "pandas"  # "pandas" | "xorq"; meaningful when mode="buckaroo"
    dataflow: Any = None  # ServerDataflow when backend="pandas"
    xorq_dataflow: Any = None  # XorqServerDataflow when backend="xorq"
    expr: Any = None  # ibis/xorq expression when backend="xorq"
    build_dir: Optional[str] = None  # xorq build dir, stored for /reload_expr
    # /load_expr cache_dir (#972): where the expr's cache nodes resolve. The
    # redirect is baked into ``expr``, so /reload_expr keeps it by reusing the
    # expr; stored so a re-POST that omits cache_dir keeps it and one that
    # changes it reloads.
    cache_dir: Optional[str] = None
    project_root: Optional[str] = None  # project root for klass discovery
    # The /load_expr dataflow config (cache_storage_path, column_config_overrides,
    # extra_grid_config, init_sd, skip_stat_columns), replayed by /reload_expr so
    # a reload keeps stat caching and column config (#957).
    dataflow_kwargs: dict = field(default_factory=dict)
    # The /load_expr stats policy. ``stats_tier`` is the tier the session is
    # headed for (see dataflow.STATS_TIERS) and ``stats_delivery`` how it gets
    # there (see STATS_DELIVERIES). Kept apart from dataflow_kwargs, which is
    # splatted into the dataflow constructor, and replayed by /reload_expr. The
    # tier the dataflow is built at follows from the pair (dataflow_stats_tier).
    stats_tier: str = DEFAULT_STATS_TIER
    stats_delivery: str = DEFAULT_STATS_DELIVERY
    # The stats generation: a counter the server owns, bumped whenever the
    # dataflow state the stats describe changes (/load, /load_expr, /load_compare,
    # /reload_expr, and a buckaroo_state_change that touches a dataflow field).
    # It rides on df_meta.stats and on every stats message, so a client can drop
    # a reply for a state it has left. Independent of any client-owned request
    # sequence (state_seq). ``stats_status`` and ``stats_reason`` live here, not
    # in ``df_meta``, because the dataflow rebuilds df_meta wholesale.
    stats_gen: int = 0
    # What ``df_meta.stats.status`` says about the stats of the current
    # ``stats_gen``: ``complete`` (the stats of the tier the session is headed for
    # are in the snapshot), ``pending`` (a deferred session that has not produced
    # them yet), ``not_computed`` (the session is headed for the schema tier, so
    # none will arrive) and ``error`` (the run failed; the next connection to
    # open retries it, see stats_wire.rearm_failed_stats).
    stats_status: str = "complete"
    stats_reason: Optional[str] = None
    # The ``df_display_args`` the full stats changed, set when a run completes
    # (a float column's minWidth reads its min and max) and carried by the
    # ``stats_update`` that delivers them, so a client whose pending frame held
    # the schema tier's config gets the stats-derived one. ``None`` while pending,
    # and when the stats left the config as it was.
    stats_display_args: Optional[dict] = None
    # Companion telemetry sink (#943): a fire-and-forget POST callable, built
    # once from the /load_expr payload's telemetry_url on the IOLoop (where
    # make_http_sink captures AsyncHTTPClient/IOLoop.current()). Stored here so
    # the WS handler — a separate async context but the same IOLoop — reuses it
    # for first-pull spans instead of rebuilding it. None when no telemetry_url
    # was supplied, which leaves telemetry_context a no-op.
    tele_sink: Optional[Callable[[Dict[str, Any]], None]] = None
    buckaroo_state: dict = field(default_factory=dict)
    # NOTE: ``search_string`` used to live here, but it's per-client typing
    # state (not a session-wide property). Two clients sharing a session
    # were clobbering each other's input via the rebroadcast path (#851).
    # It now lives on ``DataStreamHandler`` instances; this comment is the
    # tombstone so anyone reading state ordering doesn't expect it back.
    buckaroo_options: dict = field(default_factory=dict)
    command_config: dict = field(default_factory=dict)
    operation_results: dict = field(default_factory=dict)
    operations: list = field(default_factory=list)
    prompt: str = ""
    component_config: Optional[dict] = None
    last_accessed: float = field(default_factory=time.time)
    # Gates the firstpull.ws_first_payload perf span so it fires only on the
    # first infinite_request for this session (time-to-first-rows), not every
    # scroll. Flipped True after the first payload is dispatched.
    _perf_first_payload_seen: bool = False

    def touch(self) -> None:
        """Update the last-accessed timestamp."""
        self.last_accessed = time.time()

    def release_xorq_state(self) -> None:
        """Drop the xorq expression and dataflow, releasing the memtables
        xorq left on its process-wide default backend for them (#896)."""
        if self.expr is not None:
            # Lazy: xorq is optional, and an expr means it is installed.
            from buckaroo.server.xorq_loading import release_memtables  # noqa: PLC0415
            release_memtables(self.expr)
        self.expr = None
        self.xorq_dataflow = None


PROTOCOL_VERSION = 1
"""Bumped when the WebSocket protocol changes incompatibly. Clients
(WebSocketModel, TauriIPCModel) read this from initial_state and warn on
mismatch. Lockstep with the buckaroo PyPI version is the documented expectation;
this field is the runtime escape hatch."""


def begin_stats_generation(session: "SessionState") -> None:
    """Start a new stats generation: the session's dataflow state has changed,
    so stats for the previous one no longer describe it. The status restarts
    from the session's policy pair."""
    session.stats_gen += 1
    session.stats_status, session.stats_reason = initial_stats_status(
        session.stats_tier, session.stats_delivery)
    session.stats_display_args = None


def stats_meta(session: "SessionState") -> Optional[dict]:
    """The ``df_meta.stats`` value for a session: ``{status, tier, gen}`` plus
    ``reason`` when there is one. ``tier`` is the tier reached so far, which is
    the one the session is headed for only once it is complete.

    ``None`` for a session on the default policy (inline delivery, full tier,
    complete), which sends the message it always has; a client reads a missing
    ``stats`` as complete."""
    if session.stats_status == "complete" and session.stats_delivery != "deferred":
        return None
    stats: dict = {"status": session.stats_status,
        "tier": session.stats_tier if session.stats_status == "complete" else "schema",
        "gen": session.stats_gen}
    if session.stats_reason:
        stats["reason"] = session.stats_reason
    return stats


def build_state_message(session: "SessionState", metadata: dict | None = None,
                         search_string: str = "", reply_seq: int | None = None) -> dict:
    """Build the full ``initial_state`` WebSocket payload from a session.

    Args:
        session: The session whose state to serialise.
        metadata: Override metadata to include; defaults to ``session.metadata``.
        search_string: The *recipient client's* per-client live-typed
            search term (#851). Injected into ``buckaroo_state`` so the
            JS ``WebSocketModel`` — which replaces ``buckaroo_state``
            wholesale on receipt — doesn't silently clear the recipient's
            search box. The session itself never owns this value; callers
            must pass the right value per recipient (typically
            ``handler.search_string``).
        reply_seq: The ``state_seq`` of the ``buckaroo_state_change`` this
            message answers (#998). Set only on the copy sent to the client
            that made the change; that client drops a reply older than its
            latest change so an overlapping rerun can't put its
            ``buckaroo_state`` back. Omitted (``None``) for the broadcast
            copies other clients get, the ``/load`` push and a fresh
            connection, which the client applies unconditionally. Optional
            on the wire, so it doesn't bump ``PROTOCOL_VERSION``.

    Returns:
        A dict ready to be JSON-serialised and sent to WebSocket clients.
    """
    # The dataflow rebuilds df_meta wholesale, so the stats status is injected
    # here, into a copy, rather than stored in it.
    df_meta = session.df_meta
    stats = stats_meta(session)
    if stats is not None:
        df_meta = {**df_meta, "stats": stats}
    msg: dict = {"type": "initial_state", "protocol_version": PROTOCOL_VERSION,
        "metadata": metadata if metadata is not None else session.metadata,
        "prompt": session.prompt, "df_display_args": session.df_display_args, "df_data_dict": session.df_data_dict,
        "df_meta": df_meta, "mode": session.mode}
    if reply_seq is not None:
        msg["reply_seq"] = reply_seq
    if session.mode == "buckaroo":
        # Per-client search_string overlay (#851 Codex P1): the snapshot
        # on the session is search-agnostic; we re-inject the recipient's
        # value here so a missing key can't wipe it on the client.
        msg["buckaroo_state"] = {**session.buckaroo_state, "search_string": search_string}
        msg["buckaroo_options"] = session.buckaroo_options
        msg["command_config"] = session.command_config
        msg["operation_results"] = session.operation_results
        msg["operations"] = session.operations
    return msg


class SessionManager:
    """Manages session lifecycle.

    Thread-safety note: Buckaroo's server runs on a single Tornado IOLoop
    thread. All session access and mutation is expected to happen on that
    IOLoop thread. External background threads must not mutate sessions
    directly. The periodic eviction callback is scheduled via
    ``IOLoop.call_later`` so it also executes on the IOLoop thread.
    """

    def __init__(self, ttl_s: float = _DEFAULT_SESSION_TTL_S, eviction_interval_s: float = _DEFAULT_EVICTION_INTERVAL_S) -> None:
        self.sessions: dict[str, SessionState] = {}
        self._ttl_s = ttl_s
        self._eviction_interval_s = eviction_interval_s
        self._evicted_count = 0
        self._schedule_eviction()

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def _schedule_eviction(self) -> None:
        """Schedule the next eviction pass on the running Tornado IOLoop."""
        try:
            import tornado.ioloop
            tornado.ioloop.IOLoop.current().call_later(
                self._eviction_interval_s, self._evict_and_reschedule)
        except RuntimeError:
            # No IOLoop running (e.g. unit tests without an IOLoop).
            pass

    def _evict_and_reschedule(self) -> None:
        self.evict_idle_sessions()
        self._schedule_eviction()

    def evict_idle_sessions(self) -> int:
        """Remove sessions idle longer than the configured TTL.

        Only sessions with no active WebSocket clients are eligible.
        Returns the number of sessions removed.
        """
        now = time.time()
        to_evict = [
            sid
            for sid, s in self.sessions.items()
            if not s.ws_clients and (now - s.last_accessed) > self._ttl_s
        ]
        for sid in to_evict:
            self.sessions.pop(sid).release_xorq_state()
            log.info("Evicted idle session=%s", sid)
        if to_evict:
            self._evicted_count += len(to_evict)
            log.info("Evicted %d idle session(s); total_evicted=%d active=%d", len(to_evict), self._evicted_count,
                len(self.sessions))
        return len(to_evict)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @property
    def active_session_count(self) -> int:
        """Number of currently tracked sessions."""
        return len(self.sessions)

    @property
    def total_evicted_count(self) -> int:
        """Cumulative number of sessions evicted since startup."""
        return self._evicted_count

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> Optional[SessionState]:
        session = self.sessions.get(session_id)
        if session:
            session.touch()
        return session

    def create(self, session_id: str, path: str) -> SessionState:
        session = SessionState(session_id=session_id, path=path)
        self.sessions[session_id] = session
        return session

    def get_or_create(self, session_id: str, path: str) -> SessionState:
        existing = self.get(session_id)
        if existing:
            existing.path = path
            return existing
        return self.create(session_id, path)

    def add_ws_client(self, session_id: str, client) -> None:
        session = self.get(session_id)
        if not session:
            session = self.create(session_id, "")
        session.ws_clients.add(client)

    def remove_ws_client(self, session_id: str, client) -> None:
        session = self.get(session_id)
        if session:
            session.ws_clients.discard(client)
