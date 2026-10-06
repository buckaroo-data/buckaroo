"""Per-cell summary-stat cache (ADR-001, docs/plans/ADR-001-summary-stat-cache.md).

A cell is one ``(column, stat)`` value, keyed by ``(scope_id, col, stat_id)``:

* ``scope_id`` is the identity of the rows the stats ran over:
  ``make_scope_id(data_id, post_processing_hash, operations)``.
* ``stat_id`` is ``"<key>@<stat_hash>"``. ``stat_hashes`` derives each
  stat's hash from the source that defines it, the engine versions, every
  module of the buckaroo package, and the hashes of the stats it depends on,
  so editing a project stat invalidates it and its dependents and nothing
  else.

Storage is append-only parquet parts under ``<base>/<scope_id>/``. Each fill
writes one part, named so that later parts sort later; a read coalesces them
with the newest cell winning. A part has one row per dataframe column (plus a
row with a null ``col`` for table-level cells like ``length``), a
``__computed`` list column naming the stat ids computed for that row, and one
column per ``(stat_id, value type)``. The type is chosen from each value, so
an int ``min`` and a float ``min`` land in different columns and both come
back with their own type; the column's parquet field metadata names that
type. A part is verified before it's written: a value that doesn't come back
identical isn't cached. ``__computed`` is what tells "computed, and the value
is None" apart from "never computed".
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.metadata
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..dataflow.sd_cache import canonical_chain_repr
from .source_digest import callable_file, file_digest, file_md5
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


# Libraries a cached value passes through: the engine computes it
# (``approx_median`` and ``approx_nunique`` belong to the engine), then pyarrow,
# pandas and numpy carry it into the accumulator.
_ENGINE_DISTS = ("xorq", "xorq-datafusion", "pyarrow", "pandas", "numpy")


def _engine_context() -> str:
    """What every stat's value depends on besides its own source: the versions
    of ``_ENGINE_DISTS``, and every module of the buckaroo package. A stat
    reaches buckaroo code outside its own file (``histogram`` labels its
    buckets with ``customizations/histogram.py``), the pipeline runs it and
    this module encodes it, so any change to buckaroo invalidates every cell.
    Taken once, at import, for the same reason ``@stat`` takes source digests
    at definition time."""
    parts = []
    for dist in _ENGINE_DISTS:
        try:
            parts.append(f"{dist}={importlib.metadata.version(dist)}")
        except importlib.metadata.PackageNotFoundError:
            parts.append(f"{dist}=none")
    package = Path(__file__).resolve().parent.parent
    modules = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        modules.update(f"{path.relative_to(package).as_posix()}={file_digest(path)}\n".encode())
    parts.append(f"buckaroo={modules.hexdigest()}")
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
    ``scope_id`` covers.

    A stat with no source digest (compiled from a string: a notebook cell,
    ``exec``) has no hash, and neither does anything depending on it: its
    code object doesn't cover the globals it reads, so it's never cached."""
    providers = {sk.name: sf for sf in stat_funcs for sk in sf.provides}
    out: Dict[str, Optional[str]] = {}

    def visit(sf: StatFunc, path: frozenset) -> Optional[str]:
        if sf.name in out:
            return out[sf.name]
        deps = []
        uncacheable = sf.source_digest is None
        for req in sf.requires:
            if req.type in RAW_MARKER_TYPES:
                continue
            provider = providers.get(req.name)
            if provider is None or provider is sf or provider.name in path:
                deps.append(f"{req.name}=external")
                continue
            dep_hash = visit(provider, path | {sf.name})
            uncacheable = uncacheable or dep_hash is None
            deps.append(f"{req.name}={dep_hash}")
        out[sf.name] = None if uncacheable else _short_hash(
            [_ENGINE_CONTEXT, sf.name, [sk.name for sk in sf.provides], sf.source_digest, sorted(deps)])
        return out[sf.name]

    for sf in stat_funcs:
        visit(sf, frozenset())
    return {name: h for name, h in out.items() if h is not None}


def length_stat_id() -> str:
    """The table-level row count the pipeline computes with ``count()``."""
    return f"length@{_short_hash([_ENGINE_CONTEXT, 'length'])}"


def make_scope_id(data_id: Any, post_processing_hash: str = "", operations: Optional[List[Any]] = None) -> str:
    """The identity of the rows stats run over: the caller's ``data_id`` (or a
    hash of the source expression), the post-processing step (empty for the
    untransformed view), and the op chain applied to it (a search is one), in
    the canonical form the in-process SD cache keys it by."""
    key = [LAYOUT_VERSION, str(data_id), post_processing_hash, canonical_chain_repr(operations or [])]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:32]


def post_processing_hash(klass: Any) -> Optional[str]:
    """Identity of a post-processing step: the name of the file that defines
    it, the md5 of that file, and its ``post_processing_method``, since one
    file can define several steps. A loader that compiled the step from a
    file records the name and md5 it read (``source_file``, ``source_md5``);
    otherwise they come from the file defining ``post_process_df``. None when
    that file can't be read, and the step's views aren't persisted."""
    path = getattr(klass, "source_file", None)
    md5 = getattr(klass, "source_md5", None)
    if path is None:
        path = callable_file(klass.post_process_df)
        md5 = None if path is None else file_md5(path)
    if md5 is None:
        return None
    return _short_hash([os.path.basename(path), md5, klass.post_processing_method])


class CachedStatError(Exception):
    """A stat error recorded by an earlier run. Carries the message only."""


# ============================================================
# Value codec
# ============================================================
#
# Every cached value goes through an explicit codec: ``_spec`` names its type
# as a JSON tree, ``_storage_type`` maps that to an arrow type, ``_store`` and
# ``_decode`` convert the value to and from it. The spec rides in the parquet
# field's metadata, so a read never has to guess. A type the codec doesn't
# know raises ``_Uncacheable`` and the value is recomputed on every run rather
# than stored approximately. ``_identical`` is the round-trip contract: same
# type, same value, same unit and timezone, same dict key order.


class _Uncacheable(Exception):
    pass


_NULL: Dict[str, Any] = {"t": "null"}
ERROR_SPEC: Dict[str, Any] = {"t": ERROR_TAG}
_SPEC_KEY = b"buckaroo.spec"

_STORAGE_TYPES = {
    "null": pa.null(), "bool": pa.bool_(), "int": pa.int64(), "uint": pa.uint64(), "float": pa.float64(),
    "str": pa.string(), "bytes": pa.binary(), "decimal": pa.string(), "date": pa.date32(),
    "time": pa.time64("us"), "timedelta": pa.duration("us"), "np.datetime64": pa.int64(),
    "np.timedelta64": pa.int64(), "pd.Timestamp": pa.int64(), "pd.Timedelta": pa.int64(), "pd.NaT": pa.bool_(),
    "pd.Period": pa.int64(), ERROR_TAG: pa.string()}
# Stored as themselves: pyarrow converts these exactly in both directions.
_NATIVE = {"null", "bool", "int", "uint", "float", "str", "bytes", "date", "time", "timedelta", "datetime", ERROR_TAG}
_NP_STORAGE = {"b": pa.bool_(), "i": pa.int64(), "u": pa.uint64(), "f": pa.float64()}


def _spec(v: Any) -> Dict[str, Any]:
    """The type of ``v`` as a JSON-able tree. Exact types only: a subclass
    the codec doesn't name (an IntEnum, a str subclass) is uncacheable."""
    if v is None:
        return _NULL
    if v is pd.NaT:
        return {"t": "pd.NaT"}
    tv = type(v)
    if tv is bool:
        return {"t": "bool"}
    if tv is int:
        if -(2**63) <= v < 2**63:
            return {"t": "int"}
        if 0 <= v < 2**64:
            return {"t": "uint"}
        raise _Uncacheable(v)
    if tv is float:
        return {"t": "float"}
    if tv is str:
        return {"t": "str"}
    if tv is bytes:
        return {"t": "bytes"}
    if tv is Decimal:
        return {"t": "decimal"}
    if isinstance(v, np.datetime64):
        return {"t": "np.datetime64", "unit": np.datetime_data(v.dtype)[0]}
    if isinstance(v, np.timedelta64):
        return {"t": "np.timedelta64", "unit": np.datetime_data(v.dtype)[0]}
    if isinstance(v, np.generic):
        if v.dtype.kind not in _NP_STORAGE:
            raise _Uncacheable(v)
        return {"t": "np", "dtype": v.dtype.name}
    if tv is pd.Timestamp:
        return {"t": "pd.Timestamp", "unit": v.unit, "tz": None if v.tz is None else str(v.tz)}
    if tv is pd.Timedelta:
        return {"t": "pd.Timedelta", "unit": v.unit}
    if tv is pd.Period:
        return {"t": "pd.Period", "freq": v.freqstr}
    if tv is pd.Interval:
        of = _spec(v.left)
        if _spec(v.right) != of:
            raise _Uncacheable(v)
        return {"t": "pd.Interval", "closed": v.closed, "of": of}
    if tv is datetime.datetime:
        return {"t": "datetime", "tz": None if v.tzinfo is None else str(v.tzinfo)}
    if tv is datetime.date:
        return {"t": "date"}
    if tv is datetime.time:
        if v.tzinfo is not None:
            raise _Uncacheable(v)
        return {"t": "time"}
    if tv is datetime.timedelta:
        return {"t": "timedelta"}
    if tv is list or tv is tuple:
        specs: List[Dict[str, Any]] = []
        for x in v:
            s = _spec(x)
            if s != _NULL and s not in specs:
                specs.append(s)
        of = _NULL if not specs else specs[0] if len(specs) == 1 else {"t": "union", "of": specs}
        return {"t": "list" if tv is list else "tuple", "of": of}
    if tv is dict:
        if not all(type(k) is str for k in v):
            raise _Uncacheable(v)
        return {"t": "dict", "fields": [[k, _spec(x)] for k, x in v.items()]}
    raise _Uncacheable(v)


def _storage_type(spec: Dict[str, Any]) -> pa.DataType:
    t = spec["t"]
    if t in _STORAGE_TYPES:
        return _STORAGE_TYPES[t]
    if t == "datetime":
        return pa.timestamp("us", tz=spec["tz"])
    if t == "np":
        return _NP_STORAGE[np.dtype(spec["dtype"]).kind]
    if t == "pd.Interval":
        of = _storage_type(spec["of"])
        return pa.struct([("left", of), ("right", of)])
    if t in ("list", "tuple"):
        return pa.list_(_storage_type(spec["of"]))
    if t == "union":
        return pa.struct([("k", pa.int8())] + [(f"v{i}", _storage_type(s)) for i, s in enumerate(spec["of"])])
    if t == "dict":
        return pa.struct([(f"f{i}", _storage_type(s)) for i, (_k, s) in enumerate(spec["fields"])])
    raise _Uncacheable(spec)


def _store(spec: Dict[str, Any], v: Any) -> Any:
    """``v`` as the python value pyarrow builds ``_storage_type(spec)`` from."""
    if v is None:
        return None
    t = spec["t"]
    if t in _NATIVE:
        return v
    if t == "decimal":
        return str(v)
    if t == "np":
        return v.item()
    if t in ("np.datetime64", "np.timedelta64"):
        return int(v.astype(np.int64))
    if t in ("pd.Timestamp", "pd.Timedelta"):
        return v.value
    if t == "pd.NaT":
        return True
    if t == "pd.Period":
        return v.ordinal
    if t == "pd.Interval":
        return {"left": _store(spec["of"], v.left), "right": _store(spec["of"], v.right)}
    if t in ("list", "tuple"):
        return [_store(spec["of"], x) for x in v]
    if t == "union":
        k = spec["of"].index(_spec(v))
        return {"k": k, f"v{k}": _store(spec["of"][k], v)}
    if t == "dict":
        return {f"f{i}": _store(s, v[k]) for i, (k, s) in enumerate(spec["fields"])}
    raise _Uncacheable(spec)


def _decode(spec: Dict[str, Any], x: Any) -> Any:
    if x is None:
        return None
    t = spec["t"]
    if t in _NATIVE:
        return x
    if t == "decimal":
        return Decimal(x)
    if t == "np":
        return np.dtype(spec["dtype"]).type(x)
    if t == "np.datetime64":
        return np.datetime64(x, spec["unit"])
    if t == "np.timedelta64":
        return np.timedelta64(x, spec["unit"])
    if t == "pd.Timestamp":
        ts = pd.Timestamp(x, unit="ns")
        if spec["tz"] is not None:
            ts = ts.tz_localize("UTC").tz_convert(spec["tz"])
        return ts.as_unit(spec["unit"])
    if t == "pd.Timedelta":
        return pd.Timedelta(x, unit="ns").as_unit(spec["unit"])
    if t == "pd.NaT":
        return pd.NaT
    if t == "pd.Period":
        return pd.Period(ordinal=x, freq=spec["freq"])
    if t == "pd.Interval":
        return pd.Interval(_decode(spec["of"], x["left"]), _decode(spec["of"], x["right"]), closed=spec["closed"])
    if t == "list":
        return [_decode(spec["of"], e) for e in x]
    if t == "tuple":
        return tuple(_decode(spec["of"], e) for e in x)
    if t == "union":
        k = x["k"]
        return _decode(spec["of"][k], x[f"v{k}"])
    if t == "dict":
        return {k: _decode(s, x[f"f{i}"]) for i, (k, s) in enumerate(spec["fields"])}
    raise ValueError(f"unknown spec {spec!r}")


def _identical(a: Any, b: Any) -> bool:
    """The round-trip contract: same type and value, NaN equal to NaN, and
    temporals with the same unit and timezone."""
    if type(a) is not type(b):
        return False
    if a is pd.NaT:
        return b is pd.NaT
    if isinstance(a, (float, np.floating)):
        return bool(a == b) or (bool(np.isnan(a)) and bool(np.isnan(b)))
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_identical(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        return list(a) == list(b) and all(_identical(a[k], b[k]) for k in a)
    if isinstance(a, Decimal):
        return a.as_tuple() == b.as_tuple()
    if isinstance(a, (np.datetime64, np.timedelta64)):
        return a.dtype == b.dtype and (bool(a == b) or (bool(np.isnat(a)) and bool(np.isnat(b))))
    if isinstance(a, (pd.Timestamp, pd.Timedelta)):
        return bool(a == b) and a.unit == b.unit and str(getattr(a, "tz", None)) == str(getattr(b, "tz", None))
    if isinstance(a, pd.Interval):
        return a.closed == b.closed and _identical(a.left, b.left) and _identical(a.right, b.right)
    if isinstance(a, pd.Period):
        return a == b and a.freqstr == b.freqstr
    if isinstance(a, (datetime.datetime, datetime.time)):
        return a == b and str(a.tzinfo) == str(b.tzinfo)
    try:
        return bool(a == b)
    except Exception:
        return False


def _variant_name(sid: str, spec: Dict[str, Any]) -> str:
    if spec == ERROR_SPEC:
        return f"{sid}#{ERROR_TAG}"
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    return f"{sid}#{spec['t']}-{digest}"


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
                _merge_part(scope, table)
            except FileNotFoundError:
                continue  # compacted away by another process between glob and read
            except Exception as e:
                log.warning("stat cache: skipping unreadable part %s: %s", path, e)
                continue
            scope.parts_read += 1
            scope.part_paths.append(path)
        return scope

    def write(self, scope_id: str, values: Dict[Any, Dict[str, Any]],
            errors: Optional[Dict[Any, Dict[str, str]]] = None,
            keep: Optional[Callable[[str], bool]] = None) -> Optional[Path]:
        """Write one part holding ``values`` and ``errors``; returns its path,
        or None when there was nothing cacheable. Compacts the scope once it
        holds more than ``MAX_PARTS`` parts, dropping stat ids ``keep``
        rejects. A compaction failure is logged, not raised: the part is
        already on disk, and the next write retries the compaction."""
        data = _encode_part(values, errors or {})
        if data is None:
            return None
        path = self._write_bytes(scope_id, data)
        try:
            if len(self._part_paths(scope_id)) > MAX_PARTS:
                self._compact(scope_id, keep)
        except Exception as e:
            log.warning("stat cache: compacting %s failed, keeping its parts: %s", scope_id, e)
        return path

    def _write_bytes(self, scope_id: str, data: bytes) -> Path:
        scope_dir = self.scope_dir(scope_id)
        scope_dir.mkdir(parents=True, exist_ok=True)
        name = f"part-{time.time_ns():020d}-{uuid.uuid4().hex[:8]}.parquet"
        path = scope_dir / name
        tmp = scope_dir / f".{name}.tmp"
        try:
            tmp.write_bytes(data)
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
        data = _encode_part(values, errors)
        if data is not None:
            self._write_bytes(scope_id, data)
        for path in scope.part_paths:
            path.unlink(missing_ok=True)


@dataclass
class _Variant:
    """One parquet column of a part: a stat id's cells of one value type."""
    sid: str
    spec: Dict[str, Any]
    stored: List[Any]
    # Row index -> the value as the stat returned it, to verify the round trip.
    originals: Dict[int, Any] = field(default_factory=dict)


def _encode_part(values: Dict[Any, Dict[str, Any]], errors: Dict[Any, Dict[str, str]]) -> Optional[bytes]:
    """The parquet bytes of one part, or None when nothing is cacheable.

    Every cell is verified by decoding the written bytes: a cell that doesn't
    come back ``_identical`` is left out, and so is a variant parquet can't
    write. A cell left out is recomputed next time, never served wrong."""
    cols = sorted(set(values) | set(errors), key=lambda c: (c is not None, str(c)))
    computed: List[List[str]] = [[] for _ in cols]
    variants: Dict[str, _Variant] = {}
    for i, col in enumerate(cols):
        for sid, v in values.get(col, {}).items():
            if v is not None:
                try:
                    spec = _spec(v)
                    stored = _store(spec, v)
                except Exception:
                    log.debug("stat cache: %s on %r has no parquet type, not cached", sid, col)
                    continue
                var = variants.setdefault(_variant_name(sid, spec), _Variant(sid, spec, [None] * len(cols)))
                var.stored[i] = stored
                var.originals[i] = v
            computed[i].append(sid)
        for sid, msg in errors.get(col, {}).items():
            var = variants.setdefault(_variant_name(sid, ERROR_SPEC), _Variant(sid, ERROR_SPEC, [None] * len(cols)))
            var.stored[i] = var.originals[i] = str(msg)
            computed[i].append(sid)

    def drop(name: str, rows) -> None:
        var = variants[name]
        for i in list(rows):
            var.stored[i] = None
            var.originals.pop(i, None)
            computed[i].remove(var.sid)
        if not var.originals:
            del variants[name]

    for name in list(variants):
        try:
            _variant_array(variants[name])
        except Exception as e:
            log.debug("stat cache: dropping %s: %s", name, e)
            drop(name, variants[name].originals)
    # Each failed pass drops what it can't write or read back, then retries.
    for _ in range(3):
        if not any(computed):
            return None
        try:
            data = _part_bytes(cols, computed, variants)
        except Exception:
            for name in [n for n in variants if not _writes_alone(variants[n])]:
                log.debug("stat cache: dropping %s: parquet can't write it", name)
                drop(name, variants[name].originals)
            continue
        try:
            table = _read_part(data)
        except Exception:
            for name in [n for n in variants if not _reads_alone(variants[n])]:
                log.debug("stat cache: dropping %s: parquet can't read it back", name)
                drop(name, variants[name].originals)
            continue
        mismatched = {}
        for name, var in variants.items():
            try:
                back = table.column(name).to_pylist()
            except Exception:
                mismatched[name] = list(var.originals)
                continue
            bad = [i for i, v in var.originals.items() if not _round_trips(var.spec, back[i], v)]
            if bad:
                mismatched[name] = bad
        if not mismatched:
            return data
        for name, rows in mismatched.items():
            log.debug("stat cache: %s doesn't round-trip on %d row(s), not cached", name, len(rows))
            drop(name, rows)
    return None


def _variant_array(var: _Variant) -> pa.Array:
    return pa.array(var.stored, type=_storage_type(var.spec))


def _part_bytes(cols: List[Any], computed: List[List[str]], variants: Dict[str, _Variant]) -> bytes:
    fields = [pa.field(COL_FIELD, pa.string())]
    arrays = [pa.array([None if c is None else str(c) for c in cols], pa.string())]
    for name, var in variants.items():
        arr = _variant_array(var)
        fields.append(pa.field(name, arr.type, metadata={_SPEC_KEY: json.dumps(var.spec).encode()}))
        arrays.append(arr)
    fields.append(pa.field(COMPUTED_FIELD, pa.list_(pa.string())))
    arrays.append(pa.array([sorted(c) for c in computed], pa.list_(pa.string())))
    buf = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_arrays(arrays, schema=pa.schema(fields)), buf)
    return buf.getvalue().to_pybytes()


def _writes_alone(var: _Variant) -> bool:
    try:
        pq.write_table(pa.table({"v": _variant_array(var)}), pa.BufferOutputStream())
        return True
    except Exception:
        return False


def _read_part(data: bytes) -> pa.Table:
    with pq.ParquetFile(pa.BufferReader(data)) as part:
        return part.read()


def _reads_alone(var: _Variant) -> bool:
    try:
        buf = pa.BufferOutputStream()
        pq.write_table(pa.table({"v": _variant_array(var)}), buf)
        _read_part(buf.getvalue().to_pybytes())
        return True
    except Exception:
        return False


def _round_trips(spec: Dict[str, Any], stored: Any, v: Any) -> bool:
    try:
        return _identical(_decode(spec, stored), v)
    except Exception:
        return False


def _merge_part(scope: CachedScope, table: pa.Table) -> None:
    data = table.to_pydict()
    cols = data.pop(COL_FIELD)
    computed = data.pop(COMPUTED_FIELD)
    variants = []
    for name, vals in data.items():
        raw = (table.schema.field(name).metadata or {}).get(_SPEC_KEY)
        variants.append((name.rsplit("#", 1)[0], json.loads(raw) if raw else None, vals))
    for i, col in enumerate(cols):
        found: Dict[str, Any] = {}
        failed: Dict[str, str] = {}
        unreadable = set()
        for sid, spec, vals in variants:
            x = vals[i]
            if x is None:
                continue
            if spec is None:
                unreadable.add(sid)
            elif spec == ERROR_SPEC:
                failed[sid] = x
            else:
                try:
                    found[sid] = _decode(spec, x)
                except Exception:
                    unreadable.add(sid)
        col_values = scope.values.setdefault(col, {})
        col_errors = scope.errors.setdefault(col, {})
        for sid in computed[i] or ():
            if sid in unreadable:
                continue
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
