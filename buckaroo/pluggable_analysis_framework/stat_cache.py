"""Per-cell summary-stat cache (ADR-001, docs/plans/ADR-001-summary-stat-cache.md).

A cell is one ``(column, stat)`` value, keyed by ``(scope_id, col, stat_id)``:

* ``scope_id`` is the identity of the rows the stats ran over:
  ``make_scope_id(data_id, post_processing_hash)``.
* ``stat_id`` is ``"<key>@<stat_hash>"``. ``stat_hashes`` derives each
  stat's hash from the source that defines it, the engine versions, and the
  hashes of the stats it depends on, so editing a stat invalidates it and its
  dependents and nothing else.

Storage is append-only parquet parts under ``<base>/<scope_id>/``. Each fill
writes one part, named so that later parts sort later; a read coalesces them
with the newest cell winning. A part has one row per dataframe column (plus a
row with a null ``col`` for table-level cells like ``length``), a
``__computed`` list column naming the stat ids computed for that row, and one
column per ``(stat_id, value type)``. The type is chosen from each value, so
an int ``min`` and a float ``min`` land in different columns and both come
back with their own type. ``__computed`` is what tells "computed, and the
value is None" apart from "never computed".
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from .source_digest import callable_digest, file_digest
from .stat_func import RAW_MARKER_TYPES, StatFunc

log = logging.getLogger(__name__)

LAYOUT_VERSION = "v1"
# Compaction runs on write once a scope holds more parts than this.
MAX_PARTS = 8

COL_FIELD = "col"
COMPUTED_FIELD = "__computed"
ERROR_TAG = "error"


# ============================================================
# Identity
# ============================================================


def _engine_context() -> str:
    """What every stat's value depends on besides its own source: the engine
    versions (``approx_median`` and ``approx_nunique`` belong to the engine),
    and the pipeline and cache modules that execute stats and encode cells.
    Taken once, at import, for the same reason ``@stat`` takes source digests
    at definition time."""
    parts = []
    for dist in ("xorq", "xorq-datafusion"):
        try:
            parts.append(f"{dist}={importlib.metadata.version(dist)}")
        except importlib.metadata.PackageNotFoundError:
            parts.append(f"{dist}=none")
    here = Path(__file__).parent
    for module in ("xorq_stat_pipeline.py", "stat_cache.py"):
        parts.append(f"{module}={file_digest(here / module)}")
    return "|".join(parts)


_ENGINE_CONTEXT = _engine_context()


def _short_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def stat_hashes(stat_funcs: List[StatFunc]) -> Dict[str, str]:
    """``{stat func name: hash}``, a Merkle hash over the stat DAG.

    Each hash covers the stat's source digest, the keys it provides, the
    engine context, and the hashes of the stats providing its inputs. Inputs
    the pipeline supplies itself (``length``, ``dtype``, ``orig_col_name``)
    contribute their name only: they are part of the data, which
    ``scope_id`` covers."""
    providers = {sk.name: sf for sf in stat_funcs for sk in sf.provides}
    out: Dict[str, str] = {}

    def visit(sf: StatFunc, path: frozenset) -> str:
        if sf.name in out:
            return out[sf.name]
        deps = []
        for req in sf.requires:
            if req.type in RAW_MARKER_TYPES:
                continue
            provider = providers.get(req.name)
            if provider is None or provider is sf or provider.name in path:
                deps.append(f"{req.name}=external")
            else:
                deps.append(f"{req.name}={visit(provider, path | {sf.name})}")
        digest = sf.source_digest or callable_digest(sf.func)
        out[sf.name] = _short_hash(
            [_ENGINE_CONTEXT, sf.name, [sk.name for sk in sf.provides], digest, sorted(deps)])
        return out[sf.name]

    for sf in stat_funcs:
        visit(sf, frozenset())
    return out


def length_stat_id() -> str:
    """The table-level row count the pipeline computes with ``count()``."""
    return f"length@{_short_hash([_ENGINE_CONTEXT, 'length'])}"


def make_scope_id(data_id: Any, post_processing_hash: str = "") -> str:
    """The identity of the rows stats run over: the caller's ``data_id`` (or a
    hash of the source expression) plus the post-processing step, empty for
    the untransformed view."""
    return hashlib.sha256(
        json.dumps([LAYOUT_VERSION, str(data_id), post_processing_hash]).encode()).hexdigest()[:32]


def post_processing_hash(klass: Any) -> str:
    """Identity of a post-processing class: the digest its loader recorded
    (project files), else the source of its ``post_process_df``."""
    return getattr(klass, "source_digest", None) or callable_digest(klass.post_process_df)


class CachedStatError(Exception):
    """A stat error recorded by an earlier run. Carries the message only."""


# ============================================================
# Value types
# ============================================================


class _Uncacheable(Exception):
    pass


_SCALAR_TYPES = {"bool": pa.bool_(), "int": pa.int64(), "uint": pa.uint64(), "float": pa.float64(),
    "str": pa.string()}


def _type_tag(v: Any) -> str:
    """A canonical name for ``v``'s type, used as the variant column suffix.
    Values that share a tag share an arrow type. Raises ``_Uncacheable`` for
    values with no faithful parquet representation (e.g. a list mixing types)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        if -(2**63) <= v < 2**63:
            return "int"
        if 0 <= v < 2**64:
            return "uint"
        raise _Uncacheable(v)
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (list, tuple)):
        tags = {_type_tag(x) for x in v}
        if len(tags) > 1:
            raise _Uncacheable(v)
        return f"list<{tags.pop() if tags else 'empty'}>"
    if isinstance(v, dict):
        if not v or not all(isinstance(k, str) for k in v):
            raise _Uncacheable(v)
        return "struct<" + ",".join(f"{k}:{_type_tag(v[k])}" for k in sorted(v)) + ">"
    try:
        return f"arrow:{pa.scalar(v).type}"
    except Exception as e:
        raise _Uncacheable(v) from e


def _arrow_type(tag: str, sample: Any) -> Optional[pa.DataType]:
    """The arrow type for a tag's column; None lets pyarrow infer nested types."""
    if tag in _SCALAR_TYPES:
        return _SCALAR_TYPES[tag]
    if tag.startswith("arrow:"):
        return pa.scalar(sample).type
    return None


# ============================================================
# Storage
# ============================================================


@dataclass
class CachedScope:
    """The coalesced cells of one scope. ``values[col][stat_id]`` holds a
    computed value (``None`` included); ``errors[col][stat_id]`` holds the
    message of a cached stat error. Table-level cells live under ``col=None``."""
    values: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    errors: Dict[Any, Dict[str, str]] = field(default_factory=dict)
    parts_read: int = 0
    part_paths: List[Path] = field(default_factory=list)


class StatCache:
    """Append-only parquet parts per scope under ``base_path/<scope_id>/``."""

    def __init__(self, base_path: Any):
        self.base_path = Path(base_path)

    @classmethod
    def for_cache_storage_path(cls, cache_storage_path: Any) -> "StatCache":
        """The layout inside a ``/load_expr`` ``cache_storage_path``. It sits
        under ``parquet/``, the directory tallyman already clears, next to the
        per-query ``letsql_cache-snapshot-*`` files the old cache wrote."""
        return cls(Path(cache_storage_path) / "parquet" / LAYOUT_VERSION)

    def scope_dir(self, scope_id: str) -> Path:
        return self.base_path / scope_id

    def _part_paths(self, scope_id: str) -> List[Path]:
        return sorted(self.scope_dir(scope_id).glob("part-*.parquet"))

    def read(self, scope_id: str) -> CachedScope:
        scope = CachedScope()
        for path in self._part_paths(scope_id):
            try:
                # ParquetFile, not pq.read_table: the first read_table in a
                # process imports pyarrow.dataset, ~150ms on a fresh load.
                with pq.ParquetFile(path) as part:
                    table = part.read()
            except FileNotFoundError:
                continue  # compacted away by another process between glob and read
            except Exception as e:
                log.warning("stat cache: skipping unreadable part %s: %s", path, e)
                continue
            _merge_part(scope, table)
            scope.parts_read += 1
            scope.part_paths.append(path)
        return scope

    def write(self, scope_id: str, values: Dict[Any, Dict[str, Any]],
            errors: Optional[Dict[Any, Dict[str, str]]] = None,
            keep: Optional[Callable[[str], bool]] = None) -> Optional[Path]:
        """Write one part holding ``values`` and ``errors``; returns its path,
        or None when there was nothing cacheable. Compacts the scope once it
        holds more than ``MAX_PARTS`` parts, dropping stat ids ``keep``
        rejects."""
        table = _cells_to_table(values, errors or {})
        if table is None:
            return None
        path = self._write_table(scope_id, table)
        parts = self._part_paths(scope_id)
        if len(parts) > MAX_PARTS:
            self._compact(scope_id, keep)
        return path

    def _write_table(self, scope_id: str, table: pa.Table) -> Path:
        scope_dir = self.scope_dir(scope_id)
        scope_dir.mkdir(parents=True, exist_ok=True)
        name = f"part-{time.time_ns():020d}-{uuid.uuid4().hex[:8]}.parquet"
        path = scope_dir / name
        tmp = scope_dir / f".{name}.tmp"
        try:
            pq.write_table(table, tmp)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return path

    def _compact(self, scope_id: str, keep: Optional[Callable[[str], bool]]) -> None:
        """Merge every part into one. Only the parts this read saw are deleted,
        so a part another process writes meanwhile survives."""
        scope = self.read(scope_id)
        values = {col: {sid: v for sid, v in cells.items() if keep is None or keep(sid)}
            for col, cells in scope.values.items()}
        errors = {col: {sid: m for sid, m in cells.items() if keep is None or keep(sid)}
            for col, cells in scope.errors.items()}
        table = _cells_to_table(values, errors)
        if table is not None:
            self._write_table(scope_id, table)
        for path in scope.part_paths:
            path.unlink(missing_ok=True)


def _cells_to_table(values: Dict[Any, Dict[str, Any]], errors: Dict[Any, Dict[str, str]]) -> Optional[pa.Table]:
    cols = sorted(set(values) | set(errors), key=lambda c: (c is not None, str(c)))
    computed: List[List[str]] = [[] for _ in cols]
    variants: Dict[str, List[Any]] = {}
    samples: Dict[str, Any] = {}
    for i, col in enumerate(cols):
        for sid, v in values.get(col, {}).items():
            if v is not None:
                try:
                    tag = _type_tag(v)
                except _Uncacheable:
                    log.debug("stat cache: %s on %r has no parquet type, not cached", sid, col)
                    continue
                variants.setdefault(f"{sid}#{tag}", [None] * len(cols))[i] = v
                samples.setdefault(f"{sid}#{tag}", v)
            computed[i].append(sid)
        for sid, msg in errors.get(col, {}).items():
            variants.setdefault(f"{sid}#{ERROR_TAG}", [None] * len(cols))[i] = str(msg)
            computed[i].append(sid)
    if not any(computed):
        return None

    arrays: Dict[str, pa.Array] = {
        COL_FIELD: pa.array([None if c is None else str(c) for c in cols], pa.string())}
    for name, vals in variants.items():
        sid, tag = name.rsplit("#", 1)
        try:
            arrays[name] = pa.array(vals, type=pa.string() if tag == ERROR_TAG else _arrow_type(tag, samples[name]))
        except Exception as e:
            # Drop the variant; its cells are recomputed next time.
            log.debug("stat cache: dropping %s: %s", name, e)
            for i, v in enumerate(vals):
                if v is not None:
                    computed[i].remove(sid)
    arrays[COMPUTED_FIELD] = pa.array([sorted(c) for c in computed], pa.list_(pa.string()))
    return pa.table(arrays)


def _merge_part(scope: CachedScope, table: pa.Table) -> None:
    data = table.to_pydict()
    cols = data.pop(COL_FIELD)
    computed = data.pop(COMPUTED_FIELD)
    variants = [(name.rsplit("#", 1), vals) for name, vals in data.items()]
    for i, col in enumerate(cols):
        found: Dict[str, Any] = {}
        failed: Dict[str, str] = {}
        for (sid, tag), vals in variants:
            v = vals[i]
            if v is None:
                continue
            if tag == ERROR_TAG:
                failed[sid] = v
            else:
                found[sid] = v
        col_values = scope.values.setdefault(col, {})
        col_errors = scope.errors.setdefault(col, {})
        for sid in computed[i] or ():
            if sid in failed:
                col_errors[sid] = failed[sid]
                col_values.pop(sid, None)
            else:
                col_values[sid] = found.get(sid)
                col_errors.pop(sid, None)
        if not col_values:
            del scope.values[col]
        if not col_errors:
            del scope.errors[col]
