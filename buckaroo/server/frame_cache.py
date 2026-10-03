"""One eager frame per file, shared across sessions (#993).

``/load`` reads the whole file into memory. Before this cache every
session held its own copy, so two grids on the same path cost two
frames. ``FrameCache`` keys a loaded frame by the file's identity
(backend, absolute path, mtime, size) and tracks which sessions hold
it; a session that loads an unchanged file gets the frame that is
already in memory, and a frame with no holder left is dropped.

Sessions build their own dataflow over the shared frame. That is safe
because the pipeline never writes into its input frame: polars frames
are immutable through the API it uses, and on the pandas side only
``fix_df_dates`` assigns into the frame, and that is idempotent.

Single-threaded like ``SessionManager``: every call happens on the
Tornado IOLoop thread.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple

log = logging.getLogger("buckaroo.server.frame_cache")


class FrameKey(NamedTuple):
    backend: str
    path: str
    mtime_ns: int
    size: int


@dataclass
class _Entry:
    frame: Any
    holders: set[str] = field(default_factory=set)


class FrameCache:
    def __init__(self) -> None:
        self._entries: dict[FrameKey, _Entry] = {}
        self._by_session: dict[str, FrameKey] = {}

    @staticmethod
    def key_for(backend: str, path: str) -> FrameKey:
        """Stat ``path`` into a key. Raises ``FileNotFoundError`` like the
        loaders do, so the handlers' 404 branch covers it."""
        st = os.stat(path)
        return FrameKey(backend, os.path.abspath(path), st.st_mtime_ns, st.st_size)

    def acquire(self, session_id: str, backend: str, path: str, loader: Callable[[str], Any]) -> Any:
        """Return the frame for ``path``, loading it with ``loader`` only
        when no session already holds the same file version. The session's
        previous hold, if any, is released once the new frame is in hand,
        so a loader that raises leaves the session's hold as it was."""
        key = self.key_for(backend, path)
        if self._by_session.get(session_id) == key:
            return self._entries[key].frame
        entry = self._entries.get(key)
        if entry is None:
            entry = _Entry(frame=loader(path))
            self._entries[key] = entry
            log.info("frame loaded backend=%s path=%s", backend, path)
        else:
            log.info("frame shared backend=%s path=%s holders=%d", backend, path, len(entry.holders))
        self.release(session_id)
        entry.holders.add(session_id)
        self._by_session[session_id] = key
        return entry.frame

    def release(self, session_id: str) -> None:
        """Drop ``session_id``'s hold; a frame with no holder left is
        removed. No-op for a session that holds nothing."""
        key = self._by_session.pop(session_id, None)
        if key is None:
            return
        entry = self._entries[key]
        entry.holders.discard(session_id)
        if not entry.holders:
            del self._entries[key]
            log.info("frame released backend=%s path=%s", key.backend, key.path)

    def keys(self) -> list[FrameKey]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
