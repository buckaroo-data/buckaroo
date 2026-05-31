"""Tests for the server-managed initial-load cache store.

``InitialCacheStore`` is an in-memory LRU over a persistent on-disk directory,
keyed by ``data_id`` (the xorq expr hash, or a host-supplied file identity). It
backs the server's ``/load_expr`` hit path: ``prewarm`` loads bundles eagerly at
startup, ``get`` lazily faults them in from disk on a cold hit, and ``report``
feeds the ``/cache`` introspection endpoint.

``serve_window_request`` is the pure predicate deciding whether an infinite_request
can be answered from the cached first window (head slice, unsorted, unfiltered).

All pure Python — no server, no xorq. See docs/initial-load-cache-design.md.
"""
import pandas as pd

from buckaroo.cache.initial_cache import (
    DEFAULT_WINDOW, get_initial_cache_data, serve_window_request)
from buckaroo.cache.sd_codec import deserialize_sd
from buckaroo.cache.store import InitialCacheStore, write_bundle, read_bundle


def _bundle(data_id="d1", n=5):
    df = pd.DataFrame({'ints': list(range(n)), 'strs': [chr(97 + i) for i in range(n)]})
    _cid, bundle = get_initial_cache_data(df, data_id=data_id)
    return bundle


def test_put_get_memory():
    store = InitialCacheStore(base_dir=None)
    b = _bundle("d1")
    store.put(b)
    got = store.get("d1")
    assert got is b  # in-memory hit returns the same object


def test_get_missing_returns_none():
    store = InitialCacheStore(base_dir=None)
    assert store.get("nope") is None


def test_put_requires_data_id():
    store = InitialCacheStore(base_dir=None)
    b = _bundle(data_id=None)
    try:
        store.put(b)
        assert False, "expected ValueError for a bundle with no data_id"
    except ValueError:
        pass


def test_lru_eviction_memory_only():
    store = InitialCacheStore(base_dir=None, capacity=2)
    store.put(_bundle("a"))
    store.put(_bundle("b"))
    store.get("a")            # touch 'a' so 'b' is now least-recently-used
    store.put(_bundle("c"))   # over capacity → evict LRU ('b')
    assert store.get("a") is not None
    assert store.get("c") is not None
    assert store.get("b") is None  # evicted, no disk to fall back to


def test_disk_persistence_survives_new_store(tmp_path):
    base = str(tmp_path / "cache")
    s1 = InitialCacheStore(base_dir=base)
    original = _bundle("xhash")
    s1.put(original)

    # A fresh store over the same dir lazy-loads the bundle from disk.
    s2 = InitialCacheStore(base_dir=base)
    loaded = s2.get("xhash")
    assert loaded is not None
    assert loaded.config_id == original.config_id
    assert loaded.df_meta == original.df_meta
    assert loaded.first_window == original.first_window
    assert loaded.first_window_parquet == original.first_window_parquet
    assert set(deserialize_sd(loaded.sd_parquet)) == set(deserialize_sd(original.sd_parquet))
    # Simple (non-MultiIndex) df → df_display_args is plain JSON, round-trips exactly.
    assert loaded.df_display_args == original.df_display_args


def test_lru_evicts_from_memory_but_disk_backs_it(tmp_path):
    base = str(tmp_path / "cache")
    store = InitialCacheStore(base_dir=base, capacity=1)
    store.put(_bundle("a"))
    store.put(_bundle("b"))  # evicts 'a' from memory, but disk keeps it
    assert "a" not in store._mem
    assert store.get("a") is not None  # faulted back in from disk


def test_prewarm_loads_bundles(tmp_path):
    base = str(tmp_path / "cache")
    seed = InitialCacheStore(base_dir=base)
    seed.put(_bundle("one"))
    seed.put(_bundle("two"))

    fresh = InitialCacheStore(base_dir=base)
    assert fresh.prewarm() == 2
    assert "one" in fresh._mem and "two" in fresh._mem


def test_report_shape():
    store = InitialCacheStore(base_dir=None, capacity=10)
    store.put(_bundle("a"))
    store.put(_bundle("b"))
    store.get("a")
    rep = store.report()
    assert rep['count'] == 2
    assert rep['capacity'] == 10
    assert rep['total_bytes'] > 0
    by_id = {e['data_id']: e for e in rep['entries']}
    assert by_id['a']['hits'] >= 1
    assert by_id['a']['bytes'] > 0
    assert 'config_id' in by_id['a']


def test_write_read_bundle_roundtrip(tmp_path):
    d = str(tmp_path / "one")
    b = _bundle("rt")
    write_bundle(b, d)
    back = read_bundle(d)
    assert back.data_id == "rt"
    assert back.config_id == b.config_id
    assert back.first_window_parquet == b.first_window_parquet
    assert back.cache_format_version == b.cache_format_version


def test_serve_window_predicate():
    w = DEFAULT_WINDOW
    # Head slice, unsorted, unfiltered → serve from cache.
    assert serve_window_request({'start': 0, 'end': 50}, w) is True
    assert serve_window_request({'start': 0, 'end': w}, w) is True
    # Anything else falls through to the live source.
    assert serve_window_request({'start': 0, 'end': w + 1}, w) is False
    assert serve_window_request({'start': 50, 'end': 100}, w) is False
    assert serve_window_request({'start': 0, 'end': 50, 'sort': 'a'}, w) is False
    assert serve_window_request({'start': 0, 'end': 50}, w, search_string="x") is False
