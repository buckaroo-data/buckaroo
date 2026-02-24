import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
# polars is optional — only used in lazy mode

log = logging.getLogger("buckaroo.server.session")

_DEFAULT_SESSION_TTL_S = 3600.0      # 1 hour idle before eviction
_DEFAULT_EVICTION_INTERVAL_S = 300.0  # check every 5 minutes


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
    dataflow: Any = None  # ServerDataflow instance when mode="buckaroo"
    buckaroo_state: dict = field(default_factory=dict)
    buckaroo_options: dict = field(default_factory=dict)
    command_config: dict = field(default_factory=dict)
    operation_results: dict = field(default_factory=dict)
    operations: list = field(default_factory=list)
    prompt: str = ""
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update the last-accessed timestamp."""
        self.last_accessed = time.time()


def build_state_message(session: "SessionState", metadata: dict | None = None) -> dict:
    """Build the full ``initial_state`` WebSocket payload from a session.

    Args:
        session: The session whose state to serialise.
        metadata: Override metadata to include; defaults to ``session.metadata``.

    Returns:
        A dict ready to be JSON-serialised and sent to WebSocket clients.
    """
    msg: dict = {
        "type": "initial_state",
        "metadata": metadata if metadata is not None else session.metadata,
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
    return msg


class SessionManager:
    """Manages session lifecycle.

    Thread-safety note: Buckaroo's server runs on a single Tornado IOLoop
    thread. All session access and mutation is expected to happen on that
    IOLoop thread. External background threads must not mutate sessions
    directly. The periodic eviction callback is scheduled via
    ``IOLoop.call_later`` so it also executes on the IOLoop thread.
    """

    def __init__(
        self,
        ttl_s: float = _DEFAULT_SESSION_TTL_S,
        eviction_interval_s: float = _DEFAULT_EVICTION_INTERVAL_S,
    ) -> None:
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
                self._eviction_interval_s, self._evict_and_reschedule
            )
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
            del self.sessions[sid]
            log.info("Evicted idle session=%s", sid)
        if to_evict:
            self._evicted_count += len(to_evict)
            log.info(
                "Evicted %d idle session(s); total_evicted=%d active=%d",
                len(to_evict),
                self._evicted_count,
                len(self.sessions),
            )
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
