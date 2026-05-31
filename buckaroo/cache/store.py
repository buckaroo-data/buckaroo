"""Server-managed initial-load cache store.

An in-memory LRU over a persistent on-disk directory, keyed by ``data_id`` (the
xorq expr hash, or a host-supplied file identity). Backs the server's
``/load_expr`` hit path:

* ``put`` writes a bundle to memory *and* disk (so it survives a restart).
* ``get`` returns an in-memory hit directly, or lazily faults a bundle in from
  disk on a cold hit, promoting it into the LRU.
* ``prewarm`` loads every persisted bundle under a directory eagerly at startup.
* ``report`` feeds the ``/cache`` introspection endpoint.

Each bundle persists as a directory ``<base_dir>/<data_id>/`` holding a
``manifest.json`` (everything but the two parquet blobs) plus ``sd.parquet`` and
``first_window.parquet`` — binary on disk, no b64, no pickle. See
docs/initial-load-cache-design.md.
"""
import json
import logging
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from buckaroo.cache.initial_cache import InitialCacheData

log = logging.getLogger("buckaroo.cache.store")

_MANIFEST = "manifest.json"
_SD = "sd.parquet"
_WINDOW = "first_window.parquet"
_DEFAULT_CAPACITY = 64

# A manifest is the bundle minus the two parquet byte blobs (stored as sibling
# files). Keys match InitialCacheData field names so read_bundle can splat them.
_MANIFEST_FIELDS = ('config_id', 'data_id', 'df_meta', 'column_schema', 'first_window',
    'df_display_args', 'buckaroo_options', 'command_config', 'styling_klasses', 'cache_format_version')


def write_bundle(bundle: InitialCacheData, dir_path: str) -> None:
    """Persist a bundle to ``dir_path`` as manifest.json + two parquet files."""
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, _SD), 'wb') as fh:
        fh.write(bundle.sd_parquet)
    with open(os.path.join(dir_path, _WINDOW), 'wb') as fh:
        fh.write(bundle.first_window_parquet)
    manifest = {f: getattr(bundle, f) for f in _MANIFEST_FIELDS}
    # Write the manifest last, tmp-then-rename, so a crash mid-write can't leave a
    # half-written manifest that prewarm would later choke on (the manifest's
    # presence is the "this bundle is complete" signal).
    tmp = os.path.join(dir_path, _MANIFEST + '.tmp')
    with open(tmp, 'w') as fh:
        json.dump(manifest, fh)
    os.replace(tmp, os.path.join(dir_path, _MANIFEST))


def read_bundle(dir_path: str) -> InitialCacheData:
    """Inverse of ``write_bundle``."""
    with open(os.path.join(dir_path, _MANIFEST)) as fh:
        manifest = json.load(fh)
    with open(os.path.join(dir_path, _SD), 'rb') as fh:
        sd_parquet = fh.read()
    with open(os.path.join(dir_path, _WINDOW), 'rb') as fh:
        first_window_parquet = fh.read()
    return InitialCacheData(sd_parquet=sd_parquet, first_window_parquet=first_window_parquet, **manifest)


class InitialCacheStore:
    """In-memory LRU over an optional persistent on-disk directory.

    ``base_dir=None`` makes the store memory-only (handy for tests and hosts that
    don't want disk). LRU eviction only drops from memory — disk is the durable
    layer, so an evicted entry faults back in on the next ``get``.
    """

    def __init__(self, base_dir: Optional[str] = None, capacity: int = _DEFAULT_CAPACITY) -> None:
        self.base_dir = os.path.expanduser(base_dir) if base_dir else None
        self.capacity = capacity
        self._mem: "OrderedDict[str, InitialCacheData]" = OrderedDict()
        self._hits: Dict[str, int] = {}
        self._disk_loads = 0
        self._misses = 0

    def _bundle_dir(self, data_id: str) -> Optional[str]:
        return os.path.join(self.base_dir, data_id) if self.base_dir else None

    def put(self, bundle: InitialCacheData) -> None:
        data_id = bundle.data_id
        if not data_id:
            raise ValueError("bundle.data_id is required to store a bundle")
        self._mem[data_id] = bundle
        self._mem.move_to_end(data_id)
        self._hits.setdefault(data_id, 0)
        if self.base_dir:
            try:
                write_bundle(bundle, self._bundle_dir(data_id))
            except Exception as e:
                log.warning("initial-cache: failed to persist bundle %s: %r", data_id, e)
        self._evict_overflow()

    def get(self, data_id: str) -> Optional[InitialCacheData]:
        if data_id in self._mem:
            self._mem.move_to_end(data_id)
            self._hits[data_id] = self._hits.get(data_id, 0) + 1
            return self._mem[data_id]
        bundle = self._load_from_disk(data_id)
        if bundle is None:
            self._misses += 1
            return None
        self._mem[data_id] = bundle
        self._mem.move_to_end(data_id)
        self._hits[data_id] = self._hits.get(data_id, 0) + 1
        self._disk_loads += 1
        self._evict_overflow()
        return bundle

    def __contains__(self, data_id: str) -> bool:
        if data_id in self._mem:
            return True
        d = self._bundle_dir(data_id)
        return bool(d and os.path.isfile(os.path.join(d, _MANIFEST)))

    def _load_from_disk(self, data_id: str) -> Optional[InitialCacheData]:
        d = self._bundle_dir(data_id)
        if not d or not os.path.isfile(os.path.join(d, _MANIFEST)):
            return None
        try:
            return read_bundle(d)
        except Exception as e:
            log.warning("initial-cache: failed to read persisted bundle %s: %r", data_id, e)
            return None

    def _evict_overflow(self) -> None:
        # Memory-only eviction — the on-disk copy (if any) remains the durable
        # layer and is faulted back in on a later get().
        while len(self._mem) > self.capacity:
            self._mem.popitem(last=False)

    def prewarm(self, dir_path: Optional[str] = None) -> int:
        """Eagerly load every persisted bundle under ``dir_path`` (default
        ``base_dir``) into memory. Returns the count loaded."""
        dir_path = dir_path or self.base_dir
        if not dir_path or not os.path.isdir(dir_path):
            return 0
        loaded = 0
        for name in sorted(os.listdir(dir_path)):
            sub = os.path.join(dir_path, name)
            if not os.path.isfile(os.path.join(sub, _MANIFEST)):
                continue
            try:
                bundle = read_bundle(sub)
            except Exception as e:
                log.warning("initial-cache: prewarm skipped %s: %r", sub, e)
                continue
            key = bundle.data_id or name
            self._mem[key] = bundle
            self._hits.setdefault(key, 0)
            loaded += 1
        self._evict_overflow()
        return loaded

    def entries(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for data_id, bundle in self._mem.items():
            out.append({
                'data_id': data_id,
                'config_id': bundle.config_id,
                'bytes': len(bundle.sd_parquet) + len(bundle.first_window_parquet),
                'hits': self._hits.get(data_id, 0),
                'total_rows': bundle.first_window.get('total_rows')})
        return out

    def report(self) -> Dict[str, Any]:
        """Introspection payload for the ``/cache`` endpoint."""
        entries = self.entries()
        return {
            'entries': entries,
            'count': len(entries),
            'capacity': self.capacity,
            'total_bytes': sum(e['bytes'] for e in entries),
            'disk_loads': self._disk_loads,
            'misses': self._misses,
            'base_dir': self.base_dir}
