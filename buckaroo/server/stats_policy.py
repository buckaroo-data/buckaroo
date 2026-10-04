"""Which stats tier an entry should reach, decided from its size.

Pure functions, so the policy can be tested without a backend. The load
handlers resolve it (``stats_wire.resolve_session_policy``), the session applies
a forced tier on top of it (``session.effective_stats_policy``) and a
``stats_request`` is judged against it.

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

:func:`demand_columns` is the demand scan: which columns a built display config
needs ``min`` and ``max`` for even when the policy computes no stats.

The thresholds are PROVISIONAL. They are the values the phase-0 measurements
proposed (one Apple M4 Pro, 115 tallyman telemetry loads, xorq stats on
parquet and CSV slices, eager polars RSS), and they rest on gaps: the
telemetry has nothing between 11.8M and 42.3M rows, nothing was measured on
the xorq side above 12M rows, and the scalar ceiling is an extrapolation.
They live in the ``DEFAULT_*`` constants below, each with the measurement it
comes from, and each has an environment override that is read on every call,
not at import. A value that is not a non-negative integer is ignored with a
warning.

* ``BUCKAROO_STATS_FULL_AUTO_ROWS`` (12,000,000 rows) and
  ``BUCKAROO_STATS_FULL_AUTO_CELLS`` (520,000,000 cells): ``full`` is chosen
  automatically while both hold.
* ``BUCKAROO_STATS_SCALAR_AUTO_CELLS`` (1,000,000,000 cells): otherwise
  ``scalar`` is chosen automatically up to this many cells (rows x columns).
  Above it the entry stays at ``schema``.
* ``BUCKAROO_STATS_CEILING_FULL_ROWS`` (25,000,000 rows) and
  ``BUCKAROO_STATS_CEILING_FULL_CELLS`` (1,000,000,000 cells): hard ceiling
  on ``full``, refused above either bound, including for a forced request.
* ``BUCKAROO_STATS_CEILING_SCALAR_CELLS`` (4,000,000,000 cells): hard ceiling
  on ``scalar``, in cells. Above it only ``schema`` is allowed. This number
  is an extrapolation with no measurement behind it.
* ``BUCKAROO_POLARS_ROUTE_ROWS`` (8,000,000 rows): R for
  :func:`route_polars_entry`. A memory threshold, set apart from the stats
  ones, and sized for ``pre_limit`` False (see the constant below).
"""
from __future__ import annotations

import logging
import operator
import os
from dataclasses import dataclass
from typing import Any

import pyarrow.parquet as pq

log = logging.getLogger("buckaroo.server.stats_policy")

# Provisional values from the phase-0 measurements; see the module docstring.
# 105 of 115 telemetry loads are at or below 12M rows (stats p90 4.4 s). Every
# load above it is one of three CSV unions (42.3M, 54.1M, 78.0M rows) at 75,
# 114 and 215 s.
DEFAULT_FULL_AUTO_ROWS: int = 12_000_000
# Parquet 12M x 43 (516M cells) full stats took 2.9 s over 8 repetitions. The
# bound only bites on an entry wider than 43 columns at 12M rows.
DEFAULT_FULL_AUTO_CELLS: int = 520_000_000
# The scalar class costs 1.1-1.3 ms per Mcell on a parquet scan and 3-6 ms on a
# CSV union. At the worst telemetry batch rates (30-48 ms per Mcell, scalar
# being 0.44-0.71 of the batch) that is about 20-34 s at 1.0B cells.
DEFAULT_SCALAR_AUTO_CELLS: int = 1_000_000_000
# The ceiling on full separates the slowest in-limit load (11.8M rows, 22 s)
# from the fastest one above it (42.3M rows, 75 s). 25M rows and 1.0B cells are
# near the geometric midpoint of that gap (22M rows, 1.0B cells), and it is a
# gap in the telemetry, so the true limit could sit anywhere inside it.
DEFAULT_CEILING_FULL_ROWS: int = 25_000_000
DEFAULT_CEILING_FULL_CELLS: int = 1_000_000_000
# An extrapolation with no measurement behind it. The only evidence above 1.8B
# cells is the 3.36B-cell entry whose batch took 162.5 s, and scalar was not
# measured there. ``None`` means no ceiling.
DEFAULT_CEILING_SCALAR_CELLS: int | None = 4_000_000_000
# Eager polars RSS is 0.28 GB + 0.543 GB per Mrow, and with ``pre_limit`` False
# a sorted window peaks at 0.23 + 1.62 GB per Mrow (3.0x the frame). With a
# 32 GB budget, four files resident and one window in flight, 8M rows is 27 GB
# and 10M is 33.5 GB. That figure assumes ``pre_limit`` False; main's 1M
# ``pre_limit`` windows do not copy the frame and the resident-only bound would
# be about 14M rows.
DEFAULT_POLARS_ROUTE_ROWS: int = 8_000_000

# Environment variable -> StatsLimits field.
_ENV_FIELDS = {"BUCKAROO_STATS_FULL_AUTO_ROWS": "full_auto_rows",
    "BUCKAROO_STATS_SCALAR_AUTO_CELLS": "scalar_auto_cells", "BUCKAROO_STATS_CEILING_FULL_ROWS": "ceiling_full_rows",
    "BUCKAROO_STATS_CEILING_SCALAR_CELLS": "ceiling_scalar_cells", "BUCKAROO_POLARS_ROUTE_ROWS": "polars_route_rows",
    "BUCKAROO_STATS_FULL_AUTO_CELLS": "full_auto_cells", "BUCKAROO_STATS_CEILING_FULL_CELLS": "ceiling_full_cells"}

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
    # Added after the first five fields, so a positional construction keeps its meaning.
    full_auto_cells: int = DEFAULT_FULL_AUTO_CELLS
    ceiling_full_cells: int = DEFAULT_CEILING_FULL_CELLS

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
    if rows <= limits.full_auto_rows and cells <= limits.full_auto_cells:
        return "full"
    if cells <= limits.scalar_auto_cells:
        return "scalar"
    return "schema"


def _ceiling_tier(rows: int, cells: int, limits: StatsLimits) -> str:
    """The highest tier any caller may reach for an entry of this size."""
    if limits.ceiling_scalar_cells is not None and cells > limits.ceiling_scalar_cells:
        return "schema"
    if rows <= limits.ceiling_full_rows and cells <= limits.ceiling_full_cells:
        return "full"
    return "scalar"


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

    Eager polars holds about 6.8 GB at 12M rows and cannot hold the 78M-row
    entry, so a host sends entries above R to ``/load_expr`` instead of
    ``/load`` with ``backend="polars"``. R is ``limits.polars_route_rows``,
    8M rows by default. That figure assumes ``PolarsServerSampling.pre_limit``
    is False, so a sorted window copies the frame (3.0x its size at the peak);
    with the 1M ``pre_limit`` on main windows do not copy it and the same
    memory budget would allow about 14M rows. ``cols`` is accepted so the rule
    can become a cell budget without a signature change; only ``rows`` decides
    today.
    """
    rows = _count("rows", rows)
    _count("cols", cols)
    if limits is None:
        limits = StatsLimits.from_env()
    return "xorq" if rows > limits.polars_route_rows else "eager"


def demand_columns(display_args: Any, pairs: Any) -> list[str]:
    """The columns a display config reads ``histogram_bins`` of: the
    ``val_column`` of every ``color_map_config`` whose ``color_rule`` is
    ``color_map``, in any display of ``display_args`` (``df_display_args``). The
    scan reads the config alone, so it sends no query. It covers the rules a host
    put in the column overrides and the ones a klass adds at style time, since
    both are in the config once it is built.

    ``pairs`` are the ``(original, rewritten)`` names of the table's columns. A
    ``val_column`` may be either, and a rewritten name wins over an original
    that looks like one, as the client reads it; one that is neither (or not a
    string) names no column and is dropped. A ``color_map`` rule with no
    ``val_column`` reads nothing, and neither does a categorical rule or a
    tooltip. The result is the rewritten names, once each, in the table's order;
    ``display_args`` is not changed and may have any shape."""
    wanted = set()
    for display in display_args.values() if isinstance(display_args, dict) else ():
        config = display.get("df_viewer_config") if isinstance(display, dict) else None
        columns = config.get("column_config") if isinstance(config, dict) else None
        for column in columns if isinstance(columns, list) else ():
            rule = column.get("color_map_config") if isinstance(column, dict) else None
            val_column = rule.get("val_column") if isinstance(rule, dict) else None
            if isinstance(val_column, str) and rule.get("color_rule") == "color_map":
                wanted.add(val_column)
    by_name = {**{orig: new for orig, new in pairs}, **{new: new for _orig, new in pairs}}
    named = {by_name[name] for name in wanted if name in by_name}
    return [new for _orig, new in pairs if new in named]


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
