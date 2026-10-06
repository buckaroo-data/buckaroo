"""Which stats tier an entry should reach, decided from its size.

Pure functions. Nothing in the handlers, the session or the dataflow imports
this module yet; it exists so the policy can be tested without a backend
before it is wired in.

Tiers, lowest to highest:

* ``schema``: dtype, ``_type``, identity keys and the row count. Never
  requested automatically.
* ``scalar``: adds ``null_count``, ``min``, ``max``, ``mean``, ``std``,
  ``empty_count`` and ``histogram_bins``. No histogram query,
  ``value_counts``, median or (on xorq) ``distinct_count``.
* ``full``: today's stats.

:func:`resolve_stats_policy` picks the tier. A hard ceiling is applied inside
it, so the result is the lower of the requested tier and the ceiling tier
whoever asks (a load, ``/reload_expr`` or a ``stats_request`` with ``force``).
A host tier can lower the result freely and raise it only up to the ceiling.
Eager pandas and polars resolve to ``full``: their stats sample 50,000 rows,
so the cost does not grow with the file.

:func:`route_polars_entry` is the separate size rule for polars: an entry
above R rows belongs on xorq's ``/load_expr``, not eager ``/load``.

The thresholds are PROVISIONAL. They are proposals taken from repo constants
and a few tallyman telemetry entries, and calibration measurements are
expected to replace them. They live in the ``DEFAULT_*`` constants below, and each has an
environment override that is read on every call, not at import. A value that
is not a non-negative integer is ignored with a warning.

* ``BUCKAROO_STATS_FULL_AUTO_ROWS`` (10,000,000 rows): ``full`` is chosen
  automatically up to this many rows.
* ``BUCKAROO_STATS_SCALAR_AUTO_CELLS`` (500,000,000 cells): above the full
  threshold, ``scalar`` is chosen automatically up to this many cells
  (rows x columns), from the 0.40-0.54 s scalar batch on 464M cells. Above it
  the entry stays at ``schema``.
* ``BUCKAROO_STATS_CEILING_FULL_ROWS`` (50,000,000 rows): hard ceiling on
  ``full``. It has to refuse the 78M-row entry whose stats took 215 s; the
  number itself has no other evidence behind it.
* ``BUCKAROO_STATS_CEILING_SCALAR_CELLS`` (unset, no ceiling): hard ceiling
  on ``scalar``, in cells. Above it only ``schema`` is allowed.
* ``BUCKAROO_POLARS_ROUTE_ROWS`` (10,000,000 rows): R for
  :func:`route_polars_entry`. A memory threshold, set apart from the stats
  ones.
"""
from __future__ import annotations

import logging
import operator
import os
from dataclasses import dataclass
from typing import Any

import pyarrow.parquet as pq

log = logging.getLogger("buckaroo.server.stats_policy")

# Provisional values; see the module docstring.
DEFAULT_FULL_AUTO_ROWS: int = 10_000_000
DEFAULT_SCALAR_AUTO_CELLS: int = 500_000_000
DEFAULT_CEILING_FULL_ROWS: int = 50_000_000
DEFAULT_CEILING_SCALAR_CELLS: int | None = None
DEFAULT_POLARS_ROUTE_ROWS: int = 10_000_000

# Environment variable -> StatsLimits field.
_ENV_FIELDS = {"BUCKAROO_STATS_FULL_AUTO_ROWS": "full_auto_rows",
    "BUCKAROO_STATS_SCALAR_AUTO_CELLS": "scalar_auto_cells", "BUCKAROO_STATS_CEILING_FULL_ROWS": "ceiling_full_rows",
    "BUCKAROO_STATS_CEILING_SCALAR_CELLS": "ceiling_scalar_cells", "BUCKAROO_POLARS_ROUTE_ROWS": "polars_route_rows"}

# Lowest to highest.
TIERS = ("schema", "scalar", "full")

# Backends whose stats cost does not grow with the file.
EAGER_BACKENDS = frozenset({"pandas", "polars"})


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        log.warning("%s=%r is not a non-negative integer; using the default", name, raw)
        return None
    return value


@dataclass(frozen=True)
class StatsLimits:
    """The thresholds :func:`resolve_stats_policy` and
    :func:`route_polars_entry` read. ``ceiling_scalar_cells=None`` means
    ``scalar`` has no ceiling."""
    full_auto_rows: int = DEFAULT_FULL_AUTO_ROWS
    scalar_auto_cells: int = DEFAULT_SCALAR_AUTO_CELLS
    ceiling_full_rows: int = DEFAULT_CEILING_FULL_ROWS
    ceiling_scalar_cells: int | None = DEFAULT_CEILING_SCALAR_CELLS
    polars_route_rows: int = DEFAULT_POLARS_ROUTE_ROWS

    @classmethod
    def from_env(cls) -> StatsLimits:
        """The defaults with any ``BUCKAROO_*`` overrides applied."""
        overrides = {}
        for name, field in _ENV_FIELDS.items():
            value = _env_int(name)
            if value is not None:
                overrides[field] = value
        return cls(**overrides)


def _count(name: str, value: Any) -> int:
    try:
        count = operator.index(value)
    except TypeError:
        raise TypeError(f"{name} must be an integer, got {value!r}") from None
    if count < 0:
        raise ValueError(f"{name} must not be negative, got {count}")
    return count


def _size_tier(rows: int, cells: int, limits: StatsLimits) -> str:
    """The tier the server picks on its own for an entry of this size."""
    if rows <= limits.full_auto_rows:
        return "full"
    if cells <= limits.scalar_auto_cells:
        return "scalar"
    return "schema"


def _ceiling_tier(rows: int, cells: int, limits: StatsLimits) -> str:
    """The highest tier any caller may reach for an entry of this size."""
    if limits.ceiling_scalar_cells is not None and cells > limits.ceiling_scalar_cells:
        return "schema"
    return "full" if rows <= limits.ceiling_full_rows else "scalar"


def resolve_stats_policy(backend: str, source_kind: str, rows: int, cols: int, bytes: int | None = None,
        host_tier: str | None = None, limits: StatsLimits | None = None) -> dict[str, Any]:
    """Resolve the stats tier for an entry.

    ``rows`` is the count load already took (the parquet footer's, or xorq's
    cached ``_expr_count``); this function never counts anything. ``host_tier``
    is the request's ``stats_tier`` (``None`` or ``"auto"`` for the server's
    own choice); a ``stats_request`` with ``force`` passes the tier it asks for
    here. ``limits`` defaults to :meth:`StatsLimits.from_env`.

    Returns a JSON-serialisable dict:

    * ``tier_target``: the tier the session should reach.
    * ``auto_request``: whether the client should request stats up to
      ``tier_target`` on its own. False only for ``schema``.
    * ``requestable``: tiers above ``tier_target`` that an on-demand request
      may still be granted, in ascending order, up to the ceiling.
    * ``reason``: ``None`` when ``tier_target`` is ``full``; otherwise
      ``"ceiling"`` if the ceiling clipped the request, ``"host"`` if the host
      asked for this tier, ``"size"`` if the server chose it. The ``"cost"``
      reason belongs to the cost guard and is never returned here.
    * ``estimate``: the inputs the decision rests on (``rows``, ``cols`` and
      ``bytes`` when given).

    Eager backends ignore ``host_tier``. ``source_kind`` and ``bytes`` are
    accepted for the rules that will read them (a CSV size rule, and a bytes
    threshold if calibration wants one); no threshold reads them yet.
    ``source_kind`` must be a ``str``, its vocabulary being the caller's.
    ``bytes`` is ``None`` or a non-negative integer, echoed as a plain ``int``.
    A value of the wrong type raises ``TypeError`` and a negative count
    ``ValueError``.
    """
    if not isinstance(source_kind, str):
        raise TypeError(f"source_kind must be a str, got {source_kind!r}")
    rows = _count("rows", rows)
    cols = _count("cols", cols)
    if bytes is not None:
        bytes = _count("bytes", bytes)
    if host_tier == "auto":
        host_tier = None
    if host_tier is not None and host_tier not in TIERS:
        raise ValueError(f"host_tier must be one of {TIERS} or 'auto', got {host_tier!r}")
    if limits is None:
        limits = StatsLimits.from_env()

    if backend in EAGER_BACKENDS:
        requested = ceiling = "full"
        from_host = False
    else:
        cells = rows * cols
        ceiling = _ceiling_tier(rows, cells, limits)
        from_host = host_tier is not None
        requested = host_tier or _size_tier(rows, cells, limits)

    target = min(requested, ceiling, key=TIERS.index)
    if target == "full":
        reason = None
    elif target != requested:
        reason = "ceiling"
    elif from_host:
        reason = "host"
    else:
        reason = "size"

    requestable = list(TIERS[TIERS.index(target) + 1:TIERS.index(ceiling) + 1])
    estimate: dict[str, int] = {"rows": rows, "cols": cols}
    if bytes is not None:
        estimate["bytes"] = bytes
    return {"tier_target": target, "auto_request": target != "schema", "requestable": requestable, "reason": reason,
        "estimate": estimate}


def route_polars_entry(rows: int, cols: int, limits: StatsLimits | None = None) -> str:
    """``"xorq"`` for a polars entry above R rows, ``"eager"`` otherwise.

    Eager polars holds about 6.7 GB at 10.8M rows and cannot hold the 78M-row
    entry, so a host sends entries above R to ``/load_expr`` instead of
    ``/load`` with ``backend="polars"``. R is ``limits.polars_route_rows``.
    ``cols`` is accepted so the rule can become a cell budget without a
    signature change; only ``rows`` decides today.
    """
    rows = _count("rows", rows)
    _count("cols", cols)
    if limits is None:
        limits = StatsLimits.from_env()
    return "xorq" if rows > limits.polars_route_rows else "eager"


def probe_dtypes(obj: Any) -> dict[str, str]:
    """Column name to dtype string, from the schema alone.

    Takes a pandas or polars frame (a ``LazyFrame`` is not collected) or a xorq
    expression. No row is read and no query runs.
    """
    # Polars first: reading ``LazyFrame.dtypes`` resolves the plan and warns.
    if hasattr(obj, "collect_schema"):
        pairs = obj.collect_schema().items()
    elif callable(getattr(obj, "schema", None)):
        pairs = obj.schema().items()
    elif hasattr(getattr(obj, "dtypes", None), "items"):
        pairs = obj.dtypes.items()
    else:
        raise TypeError(f"cannot read a schema from {type(obj).__name__}")
    return {str(name): str(dtype) for name, dtype in pairs}


def probe_parquet_rows(source: Any) -> int:
    """A parquet file's row count, from its footer.

    ``source`` is a path or a binary file object. Only the footer metadata is
    read, so the cost does not grow with the file (0.4 ms on 4M rows). A
    single file only; a dataset directory is not handled.
    """
    return int(pq.read_metadata(source).num_rows)
