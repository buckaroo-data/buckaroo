from dataclasses import dataclass, field
from typing import Any, Optional
# pandas is optional — only used in viewer/buckaroo modes


@dataclass
class SessionState:
    session_id: str
    path: str
    df: Optional[Any] = None  # pd.DataFrame when pandas is available
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


class SessionManager:
    def __init__(self):
        self.sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> Optional[SessionState]:
        return self.sessions.get(session_id)

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

    def add_ws_client(self, session_id: str, client):
        session = self.get(session_id)
        if not session:
            session = self.create(session_id, "")
        session.ws_clients.add(client)

    def remove_ws_client(self, session_id: str, client):
        session = self.get(session_id)
        if session:
            session.ws_clients.discard(client)
