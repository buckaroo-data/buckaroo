"""Server-side xorq loading — mirrors ``buckaroo.server.data_loading``
for the xorq backend.

Isolated module so the xorq import surface stays out of the rest of
the server. The handler in ``handlers.py`` lazy-imports this module
inside ``LoadExprHandler.post`` so a server without ``buckaroo[xorq]``
installed still imports cleanly.
"""
from __future__ import annotations

import logging
import os
import traceback
import uuid
from pathlib import Path

import pyarrow.parquet as pq

from buckaroo.server.git_state_guard import install_git_state_guard
# The project klass loaders moved to ``project_loading`` so the polars
# ``/load`` path can use them without importing xorq; re-exported here for
# the callers and tests that import them from this module.
from buckaroo.server.project_loading import (  # noqa: F401
    load_project_display_klasses, load_project_post_processing_klasses,
    load_project_stat_klasses)
from buckaroo.server.window import clamp_window
from buckaroo.serialization_utils import make_infinite_resp
from buckaroo.xorq_buckaroo import (
    NoCleaningConfXorq, XorqAutocleaning, XorqDataflow, XorqDfStatsV2,
    XorqInfiniteSampling, _XORQ_ANALYSIS_KLASSES, _expr_count,
    window_to_parquet)

log = logging.getLogger(__name__)

# xorq captures git provenance by forking `git` from the compiler; from the
# long-lived multithreaded Tornado server that fork can SIGSEGV on macOS and
# fail /load_expr with a 500 (#885). Installing the guard here — the single
# module the server imports to touch xorq — makes every xorq build/load path
# the server drives dispatch git fork-free and degrade instead of crashing.
install_git_state_guard()


def _make_cache_storage(cache_storage_path):
    """Build a ``ParquetSnapshotCache`` from a filesystem path string.

    Returns ``None`` when ``cache_storage_path`` is falsy so callers can
    check with a simple ``if self.cache_storage``.
    """
    if not cache_storage_path:
        return None
    from xorq.caching import ParquetSnapshotCache, ParquetStorage, SnapshotStrategy  # noqa: PLC0415
    storage = ParquetStorage(base_path=Path(cache_storage_path))
    return ParquetSnapshotCache(strategy=SnapshotStrategy(), storage=storage)


class XorqServerDataflow(XorqDataflow):
    """Headless XorqDataflow with infinite sampling.

    Mirrors the class-attribute set ``XorqBuckarooWidget`` injects into
    its ``InnerDataFlow`` (xorq_buckaroo.py:181-186) — without
    ``InnerDataFlow``'s widget-side ``_df_to_obj`` override, since the
    server never serialises a main-frame sample (``skip_main_serial=True``).

    ``extra_klasses`` is an optional list of additional ``@stat()``-decorated
    functions (or ``ColAnalysis`` subclasses) to fold into ``analysis_klasses``
    at the per-instance level. ``LoadExprHandler.post`` uses it to inject
    project-authored stats discovered under ``<project_root>/stats/*.py``
    and project-authored post-processing classes discovered under
    ``<project_root>/post_processing/*.py``; the built-in xorq stats are
    kept first so collisions resolve to the built-in.
    """

    sampling_klass = XorqInfiniteSampling
    autocleaning_klass = XorqAutocleaning
    autoclean_conf = (NoCleaningConfXorq,)
    DFStatsClass = XorqDfStatsV2
    analysis_klasses = _XORQ_ANALYSIS_KLASSES

    def __init__(self, expr, *args, extra_klasses=None, cache_storage_path=None, **kwargs):
        if extra_klasses:
            # Per-instance override — class-level _XORQ_ANALYSIS_KLASSES is
            # left untouched so other sessions / direct widget usage don't
            # inherit one project's stats.
            self.analysis_klasses = list(_XORQ_ANALYSIS_KLASSES) + list(extra_klasses)
        self.cache_storage = _make_cache_storage(cache_storage_path)
        super().__init__(expr, *args, **kwargs)


def load_expr_build_dir(build_dir: str, cache_dir=None):
    """Rehydrate an ibis expression from a xorq build directory.

    Wrapper around ``xorq.api.load_expr``. Build dirs that contain
    in-memory memtables (the small reference tables joined against a
    remote source) need a backend to re-read their parquet snapshot
    during rehydration. xorq's own datafusion backend is the natural
    default — it's what ``xo.connect()`` returns and what ships with
    every ``buckaroo[xorq]`` install. If the caller has already set
    a default (e.g. DuckDB), respect that.

    ``xorq.config.default_backend()`` is the xorq-internal singleton
    (cached in ``xorq.config.options.default_backend``). Calling it here
    pre-warms that singleton so xorq's own internal paths (e.g.
    ``deferred_reads_to_memtables``) reuse the same SessionContext on
    every call rather than minting a new one.

    xorq serializes only a cache node's ``relative_path``, so a loaded
    ``CachedNode`` resolves under ``~/.cache/xorq`` whatever directory the
    build was baked into. ``cache_dir`` points every parquet-backed cache
    node at that directory instead (``redirect_cache_dir``), so an embedder's
    baked snapshots are read rather than recomputed into a second copy
    (#972). Unset, xorq's default resolution is unchanged. Snapshots missing
    from ``cache_dir`` are written by ``heal_missing_snapshots``, which the
    caller runs (and times) separately."""
    from xorq.api import load_expr  # noqa: PLC0415  (lazy, see module docstring)
    from xorq.vendor import ibis  # noqa: PLC0415
    from xorq import config as xorq_config  # noqa: PLC0415
    # Pre-warm xorq's process-wide singleton. xorq.config.default_backend()
    # caches in xorq.config.options.default_backend (a separate object from
    # ibis.options.default_backend); calling it once here ensures subsequent
    # calls inside load_expr return the same SessionContext.
    con = xorq_config.default_backend()
    # Also set the ibis-vendor option for any ibis-internal paths that use it.
    if ibis.options.default_backend is None:
        ibis.options.default_backend = con
    expr = load_expr(build_dir)
    if cache_dir:
        expr = redirect_cache_dir(expr, cache_dir)
    return expr


def redirect_cache_dir(expr, cache_dir):
    """Point every parquet-backed ``CachedNode`` at ``cache_dir``.

    xorq's own ``load_expr(cache_dir=...)`` does this with
    ``expr.op().replace``, which does not descend into ``Expr``-valued fields
    (``CachedNode.parent``, ``RemoteTable.remote_expr``). A cache node nested
    in another's parent keeps ``base_path=None`` — and because a cache key
    hashes its parent's storage, the outer node then misses too.
    ``replace_nodes`` descends those fields, so every node in the closure is
    redirected."""
    # Lazy, like every xorq import here: tests import this module without
    # buckaroo[xorq] installed.
    from attr import evolve  # noqa: PLC0415
    from xorq.caching import ParquetStorage  # noqa: PLC0415
    from xorq.common.utils.graph_utils import replace_nodes  # noqa: PLC0415
    from xorq.expr.relations import CachedNode  # noqa: PLC0415
    cache_dir = Path(cache_dir)

    def replacer(node, kwargs):
        if kwargs:
            node = node.__recreate__(kwargs)
        if isinstance(node, CachedNode) and isinstance(node.cache.storage, ParquetStorage):
            cache = evolve(node.cache, storage=evolve(node.cache.storage, base_path=cache_dir))
            return node.__recreate__(dict(zip(node.__argnames__, node.__args__)) | {"cache": cache})
        return node

    return replace_nodes(replacer, expr).to_expr()


def _outermost_cache_nodes(expr):
    """The ``CachedNode``s reachable from ``expr`` without passing through
    another one: the snapshots a query of ``expr`` reads first."""
    from xorq.common.utils.graph_utils import gen_children_of, to_node  # noqa: PLC0415
    from xorq.expr.relations import CachedNode  # noqa: PLC0415
    seen, found, stack = set(), [], [to_node(expr)]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        if isinstance(node, CachedNode):
            found.append(node)
        else:
            stack.extend(gen_children_of(node))
    return found


def _write_snapshot(parent, path: Path, parquet_metadata=None):
    """Execute ``parent`` into the parquet snapshot at ``path``.

    The rows go to a temp file no other writer uses, which ``os.replace``
    then moves into place atomically: the snapshot appears whole or not at
    all, and another writer of the same key costs duplicate work, never a
    corrupt file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with parent.to_pyarrow_batches() as batches:
            schema = batches.schema
            if parquet_metadata:
                schema = schema.with_metadata((schema.metadata or {}) | parquet_metadata)
            with pq.ParquetWriter(str(tmp_path), schema) as writer:
                for batch in batches:
                    writer.write_batch(batch)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def heal_missing_snapshots(expr):
    """Write the parquet snapshots a query of ``expr`` would find missing,
    and return their paths.

    With a shared ``cache_dir`` the server is a second writer into the
    embedder's cache. xorq's ``ParquetStorage.put`` writes through a fixed
    ``<key>.parquet.tmp``, so two writers of one key can clobber each
    other's partial file and leave a corrupt snapshot that ``exists()``
    reports as a hit. The heal writes each snapshot itself instead, through
    ``_write_snapshot``, and takes no lock that another process could hold.

    The walk follows xorq's lazy read path. A cache node whose snapshot
    exists answers every query below it, so nothing under it is touched. A
    missing one first has the snapshots its parent reads healed, so running
    the parent reads them rather than having xorq ``put`` them. Only the
    root's snapshot gets provenance, as in xorq's executor.

    Each write is logged: against a baked cache it usually means
    ``cache_dir`` is spelled differently from the path the embedder baked
    with, which xorq hashes into the key of every cache node above
    another."""
    from xorq.caching import ParquetStorage  # noqa: PLC0415
    from xorq.common.utils.provenance_utils import build_provenance_metadata  # noqa: PLC0415
    root = expr.op()
    visited = set()
    written = []

    def heal(node):
        if node in visited:
            return
        visited.add(node)
        cache = node.cache
        key = cache.calc_key(node.parent)
        if cache.storage.exists(key):
            return
        for inner in _outermost_cache_nodes(node.parent):
            heal(inner)
        # Any other storage is left for xorq to write at query time.
        if not isinstance(cache.storage, ParquetStorage):
            return
        path = Path(cache.storage.get_path(key))
        metadata = (build_provenance_metadata(expr, cache.strategy, cache.storage)
            if node is root else None)
        log.info("cache_dir heal: writing missing snapshot %s", path)
        _write_snapshot(node.parent, path, metadata)
        written.append(path)

    for node in _outermost_cache_nodes(expr):
        heal(node)
    return written


def get_xorq_metadata(xorq_dataflow: XorqServerDataflow, build_dir: str) -> dict:
    """Metadata payload matching ``data_loading.get_metadata``'s shape."""
    expr = xorq_dataflow.processed_df
    columns = [{"name": str(name), "dtype": str(dtype)}
        for name, dtype in expr.schema().items()]
    return {"path": build_dir, "rows": _expr_count(expr), "columns": columns}


def handle_infinite_request_xorq(xorq_dataflow: XorqServerDataflow,
        payload_args: dict, search_string: str = "") -> tuple[dict, bytes]:
    """Drive one infinite_request window against a xorq expression.

    Reads the current ``processed_df`` (the expression, post-filter)
    from ``widget_args_tuple``, optionally applies a live ``search_string``
    contains-filter on top (#838 — keeps per-keystroke edits off the
    stat pipeline that ``quick_command_args.search`` triggers), then
    delegates to ``window_to_parquet`` and returns the
    ``(json_msg, parquet_bytes)`` pair the WebSocket handler ships as
    a text + binary frame pair (matching the pandas/polars paths)."""
    from buckaroo.customizations.xorq_commands import search_expr
    _unused, processed_df, merged_sd = xorq_dataflow.widget_args_tuple
    if processed_df is None:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0}, b"")

    try:
        filtered_expr = search_expr(processed_df, search_string) if search_string else processed_df

        sort = payload_args.get("sort")
        sort_col = None
        ascending = True
        if sort:
            sort_col = merged_sd[sort]["orig_col_name"]
            ascending = payload_args.get("sort_direction") == "asc"

        total_length = _expr_count(filtered_expr)
        # Clamp the request window to a bounded slice — protects
        # against ``end >> total_rows`` requests that would otherwise
        # ship the entire table in a single WS frame. See #797.
        start, end = clamp_window(
            payload_args.get("start"), payload_args.get("end"), total_length)
        parquet_bytes = window_to_parquet(filtered_expr, start, end, sort_col, ascending)
        # Native pyarrow parquet — strings are not JSON-wrapped.
        return make_infinite_resp(payload_args, total_length, parquet_bytes, json_columns=[])
    except Exception:
        return ({"type": "infinite_resp", "key": payload_args,
            "length": 0, "error_info": traceback.format_exc()}, b"")
