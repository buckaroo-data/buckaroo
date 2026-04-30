"""v2 xorq/ibis stat functions for the pluggable analysis framework.

Mirrors ``pd_stats_v2`` but using ibis expressions executed via
``XorqStatPipeline`` against an ``ibis.Table`` (DuckDB, Postgres, Snowflake,
etc.) — typically through xorq for cross-backend compute.

Stat layout:
  - **Typing**: derived from the schema dtype string (no query).
  - **Batched aggregates** (``XorqColumn`` parameter, return ibis.Expr):
    ``length``, ``null_count``, ``min``, ``max``, ``distinct_count``,
    ``mean``, ``std``, ``median``. Folded into one ``table.aggregate()``.
  - **Computed**: ``non_null_count``, ``nan_per``, ``distinct_per``.
  - **Histogram**: per-column query against the ``XorqTable``.

Usage::

    from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2
    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (
        XorqStatPipeline,
    )

    pipeline = XorqStatPipeline(XORQ_STATS_V2)
    stats, errors = pipeline.process_table(ibis_table)
"""

from __future__ import annotations

import math
from typing import TypedDict

from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (
    XorqColumn,
    XorqTable,
    XorqExecute,
)
from buckaroo.pluggable_analysis_framework.stat_func import stat

try:
    import ibis

    HAS_IBIS = True
except ImportError:
    HAS_IBIS = False


# ============================================================
# Column filters
# ============================================================


def _is_numeric_ibis(dtype) -> bool:
    """True for numeric (incl. boolean — matches ibis's own definition)."""
    return dtype.is_numeric()


def _is_numeric_not_bool(dtype) -> bool:
    return dtype.is_numeric() and not dtype.is_boolean()


# ============================================================
# Typing — derive type flags from the schema dtype string
# ============================================================

TypingResult = TypedDict(
    "TypingResult",
    {
        "is_numeric": bool,
        "is_integer": bool,
        "is_float": bool,
        "is_bool": bool,
        "is_datetime": bool,
        "is_string": bool,
    },
)


@stat()
def typing_stats(dtype: str) -> TypingResult:
    """Derive type flags from the ibis schema dtype string.

    Uses prefix matching rather than substring ``in`` — the latter would
    false-positive on hypothetical future ibis types containing "time" or
    "date" buried in their name (e.g. "lifetime"). Today the only
    temporal repr prefixes ibis emits are timestamp, date, time, interval.
    """
    is_bool = dtype == "boolean"
    is_int = any(dtype.startswith(p) for p in ("int", "uint"))
    is_float = any(dtype.startswith(p) for p in ("float", "double", "decimal"))
    is_numeric = is_int or is_float or is_bool
    is_datetime = any(
        dtype.startswith(p) for p in ("timestamp", "date", "time", "interval")
    )
    is_string = dtype in ("string", "large_string", "varchar", "utf8")
    return {
        "is_numeric": is_numeric,
        "is_integer": is_int,
        "is_float": is_float,
        "is_bool": is_bool,
        "is_datetime": is_datetime,
        "is_string": is_string,
    }


@stat()
def _type(
    is_bool: bool,
    is_integer: bool,
    is_float: bool,
    is_datetime: bool,
    is_string: bool,
) -> str:
    """Human-readable column type string."""
    if is_bool:
        return "boolean"
    if is_integer:
        return "integer"
    if is_float:
        return "float"
    if is_datetime:
        return "datetime"
    if is_string:
        return "string"
    return "obj"


# ============================================================
# Batched aggregates — one ibis.Expr each, folded into the batch query
# ============================================================
# These functions return ``ibis.Expr`` at runtime; the batch executor
# folds them into a single ``table.aggregate(...)`` call and the resulting
# scalar lands in the accumulator under the key named by ``provides=``.
# Type annotations describe the *eventual scalar type* in the accumulator.


@stat(provides="null_count")
def base_null_count(col: XorqColumn) -> int:
    return col.isnull().sum().coalesce(0).cast("int64")


@stat(provides="min", column_filter=_is_numeric_ibis)
def base_min(col: XorqColumn) -> float:
    return col.min().cast("float64")


@stat(provides="max", column_filter=_is_numeric_ibis)
def base_max(col: XorqColumn) -> float:
    return col.max().cast("float64")


@stat(provides="distinct_count")
def base_distinct_count(col: XorqColumn) -> int:
    return col.nunique().cast("int64")


@stat(provides="mean", column_filter=_is_numeric_not_bool)
def base_mean(col: XorqColumn) -> float:
    return col.mean().cast("float64")


@stat(provides="std", column_filter=_is_numeric_not_bool)
def base_std(col: XorqColumn) -> float:
    return col.std().cast("float64")


@stat(provides="median", column_filter=_is_numeric_not_bool)
def base_median(col: XorqColumn) -> float:
    return col.approx_median().cast("float64")


# ============================================================
# Computed (no XorqColumn dep) — derive from already-resolved scalars
# ============================================================


@stat()
def non_null_count(length: int, null_count: int) -> int:
    return length - null_count


@stat()
def nan_per(length: int, null_count: int) -> float:
    if not length:
        return 0.0
    return null_count / length


@stat()
def distinct_per(length: int, distinct_count: int) -> float:
    if not length:
        return 0.0
    return distinct_count / length


# ============================================================
# Histogram — per-column GROUP BY query against the ibis Table
# ============================================================


def _numeric_histogram(execute, table, col, min_val, max_val, total_rows):
    if min_val is None or max_val is None:
        return []
    if (isinstance(min_val, float) and math.isnan(min_val)) or (
        isinstance(max_val, float) and math.isnan(max_val)
    ):
        return []
    if min_val == max_val:
        return []

    bucket = (
        ((table[col].cast("float64") - min_val) / (max_val - min_val) * 10)
        .cast("int64")
        .clip(lower=0, upper=9)
    )
    query = (
        table.mutate(__bucket=bucket)
        .group_by("__bucket")
        .aggregate(__count=lambda t: t.count())
        .order_by("__bucket")
    )
    df = execute(query)
    if len(df) == 0:
        return []
    total = float(df["__count"].sum())
    if total == 0:
        return []

    bucket_width = (max_val - min_val) / 10
    out = []
    for _, row in df.iterrows():
        idx = int(row["__bucket"])
        low = min_val + idx * bucket_width
        high = low + bucket_width
        out.append(
            {
                "name": f"{low:.3g}-{high:.3g}",
                "cat_pop": float(row["__count"]) / total,
            }
        )
    return out


def _categorical_histogram(execute, table, col):
    query = (
        table.group_by(col)
        .aggregate(__count=lambda t: t.count())
        .order_by(ibis.desc("__count"))
        .limit(10)
    )
    df = execute(query)
    if len(df) == 0:
        return []
    total = float(df["__count"].sum())
    if total == 0:
        return []
    out = []
    for _, row in df.iterrows():
        out.append(
            {
                "name": str(row[col]),
                "cat_pop": float(row["__count"]) / total,
            }
        )
    return out


@stat(default=[])
def histogram(
    table: XorqTable,
    execute: XorqExecute,
    orig_col_name: str,
    is_numeric: bool,
    is_bool: bool,
    length: int,
    min: float,
    max: float,
) -> list:
    """10-bucket numeric histogram or top-10 categorical histogram.

    ``min`` and ``max`` come from the batch aggregate. The pipeline
    pre-populates them as ``None`` for every column so non-numeric cols
    (where ``base_min``/``base_max`` are filtered out) don't cascade-
    exclude this stat — the categorical branch ignores them.

    All queries go through the injected ``execute`` callable so a
    pipeline-supplied backend isn't bypassed.

    ``default=[]`` provides a graceful fallback if the histogram query
    fails (e.g. backend rejects the GROUP BY). NB: until #687 is fixed,
    the error is silently replaced by ``[]``.
    """
    if length == 0:
        return []
    if is_numeric and not is_bool:
        return _numeric_histogram(
            execute, table, orig_col_name, min, max, length
        )
    return _categorical_histogram(execute, table, orig_col_name)


# ============================================================
# Convenience list — drop into XorqStatPipeline(XORQ_STATS_V2)
# ============================================================
# NOTE: This list is for ``XorqStatPipeline`` only. ``typing_stats``
# requires ``dtype``, and ``histogram`` requires ``length``, ``min``,
# ``max`` — all four are externally pre-populated by ``XorqStatPipeline``
# but are NOT in ``StatPipeline.EXTERNAL_KEYS``, so passing this list to
# the pandas/polars ``StatPipeline`` raises ``DAGConfigError`` at
# construction. Use the pandas/polars equivalents (``PD_ANALYSIS_V2`` /
# ``PL_ANALYSIS_V2``) for those pipelines.

XORQ_STATS_V2 = [
    typing_stats,
    _type,
    base_null_count,
    base_min,
    base_max,
    base_distinct_count,
    base_mean,
    base_std,
    base_median,
    non_null_count,
    nan_per,
    distinct_per,
    histogram,
]
