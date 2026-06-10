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
  - **Histogram**: per-column query against the ``XorqExpr``.

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
from typing import Any, Callable

import pandas as pd

from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (XorqColumn, XorqExpr, XorqExecute)
from buckaroo.pluggable_analysis_framework.stat_func import MultipleProvides, stat
from buckaroo.customizations.histogram import fmt_bucket

try:
    import xorq.api as xo

    HAS_XORQ = True
except ImportError:
    HAS_XORQ = False


# ============================================================
# Column filters
# ============================================================


def _is_numeric_ibis(dtype) -> bool:
    """True for numeric (incl. boolean — matches ibis's own definition)."""
    return dtype.is_numeric()


def _is_numeric_not_bool(dtype) -> bool:
    return dtype.is_numeric() and not dtype.is_boolean()


def _not_float(dtype) -> bool:
    return not dtype.is_floating()


# ============================================================
# Typing — derive type flags from the schema dtype string
# ============================================================

class TypingResult(MultipleProvides):
    is_numeric: bool
    is_integer: bool
    is_float: bool
    is_bool: bool
    is_datetime: bool
    is_string: bool


@stat()
def typing_stats(dtype: str) -> TypingResult:
    """Derive type flags from the ibis schema dtype string.

    ``dtype`` is left as ``str`` rather than an enum / Literal because
    ibis dtype reprs are open-ended: parametrised forms like
    ``decimal(10, 2)``, ``timestamp('UTC')``, ``array<int64>``, and
    ``struct<a: int64, b: string>`` cannot be enumerated up front. We
    match by prefix instead.

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
        dtype.startswith(p) for p in ("timestamp", "date", "time", "interval"))
    is_string = dtype in ("string", "large_string", "varchar", "utf8")
    return {"is_numeric": is_numeric, "is_integer": is_int, "is_float": is_float, "is_bool": is_bool,
        "is_datetime": is_datetime, "is_string": is_string}


@stat()
def _type(is_bool: bool, is_integer: bool, is_float: bool, is_datetime: bool, is_string: bool) -> str:
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
# scalar lands in the accumulator under the key matching the function name.
# Type annotations describe the *eventual scalar type* in the accumulator.
#
# Names like ``min`` / ``max`` shadow the corresponding builtins inside this
# module — intentional. Module-internal code never calls ``builtins.min`` /
# ``max``; aggregations go through ``col.min()`` / ``col.max()`` (ibis
# methods on the column expression).


@stat()
def null_count(col: XorqColumn) -> int:
    return col.isnull().sum().coalesce(0).cast("int64")


@stat(column_filter=_is_numeric_ibis)
def min(col: XorqColumn) -> float:
    return col.min().cast("float64")


@stat(column_filter=_is_numeric_ibis)
def max(col: XorqColumn) -> float:
    return col.max().cast("float64")


@stat(column_filter=_not_float)
def distinct_count(col: XorqColumn) -> int:
    """Approximate distinct count (HyperLogLog, ~1% error) where supported.

    Exact COUNT(DISTINCT) folded into the shared batch aggregate defeats
    DataFusion's single-distinct rewrite: 3.8GB peak on a 131M-row string
    column with 6.2M distinct values vs 238MB for approx_nunique in the
    same batch shape (#906). No consumer needs exactness — distinct_per
    is displayed as a ratio, and the histogram branch thresholds
    (distinct_count > 5 / <= 5) sit where HLL is exact in practice.

    Float columns skip the stat entirely (column_filter): DataFusion's
    approx_distinct raises on Float64, exact COUNT(DISTINCT) costs memory
    proportional to cardinality (~2.2GB measured on a 30M-distinct float
    column), and a distinct count over floats is rarely meaningful. The
    pipeline pre-populates ``distinct_count`` as None so dependents
    (histogram, histogram_bins, distinct_per) still run.

    Allowlist, not denylist, for the remaining dtypes: approx_distinct
    raises for other unimplemented dtypes too (Boolean at least), and one
    failing expression aborts the entire batch aggregate — every batched
    stat for every column. Unverified dtypes keep the exact aggregate;
    the memory blowup is dominated by high-cardinality string columns,
    which are covered.
    """
    dt = col.type()
    if dt.is_string() or dt.is_integer() or dt.is_timestamp() or dt.is_date():
        return col.approx_nunique().cast("int64")
    return col.nunique().cast("int64")


@stat(column_filter=_is_numeric_not_bool)
def mean(col: XorqColumn) -> float:
    return col.mean().cast("float64")


@stat(column_filter=_is_numeric_not_bool)
def std(col: XorqColumn) -> float:
    return col.std().cast("float64")


@stat(column_filter=_is_numeric_not_bool)
def median(col: XorqColumn) -> float:
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
    if distinct_count is None:
        # Float columns skip distinct_count; the ratio is undefined.
        return None
    if not length:
        return 0.0
    return distinct_count / length


# ============================================================
# Histogram — per-column GROUP BY query against the ibis Table
# ============================================================


def _numeric_histogram(execute: Callable[[Any], pd.DataFrame], expr: Any, col: str, min_val: float,
        max_val: float) -> list:
    if min_val is None or max_val is None:
        return []
    if (isinstance(min_val, float) and math.isnan(min_val)) or (
        isinstance(max_val, float) and math.isnan(max_val)
    ):
        return []
    if min_val == max_val:
        return []

    bucket = (
        ((expr[col].cast("float64") - min_val) / (max_val - min_val) * 10)
        .cast("int64")
        .clip(lower=0, upper=9)
    )
    query = (
        expr.mutate(__bucket=bucket)
        .group_by("__bucket")
        .aggregate(__count=lambda t: t.count())
        .order_by("__bucket")
    )
    df = execute(query)
    if len(df) == 0:
        return []
    # Nulls in ``col`` produce a NULL ``__bucket`` row; drop it so
    # ``int(row["__bucket"])`` below doesn't raise on NaN. Without this,
    # any column with even one null silently lost its histogram via the
    # ``default=[]`` fallback on ``histogram``.
    df = df[df["__bucket"].notna()]
    if len(df) == 0:
        return []
    total = float(df["__count"].sum())
    if total == 0:
        return []

    bucket_width = (max_val - min_val) / 10
    ref = abs(max_val) if abs(max_val) >= abs(min_val) else abs(min_val)
    out = []
    for _, row in df.iterrows():
        idx = int(row["__bucket"])
        low = min_val + idx * bucket_width
        high = low + bucket_width
        out.append(
            {"name": fmt_bucket(low, high, bucket_width, ref),
             "population": round(float(row["__count"]) / total * 100, 1)})
    return out


# Above this many rows the exact top-10 query is replaced by one over a
# ~CATEGORICAL_HISTOGRAM_SAMPLE_ROWS row sample. The exact query holds a
# hash entry per distinct value just to return 10 rows — ~1GB transient
# per high-cardinality string column (#907). Sampling bounds the group-by
# input (and therefore the hash state) to the sample size.
CATEGORICAL_HISTOGRAM_EXACT_MAX_ROWS = 100_000
CATEGORICAL_HISTOGRAM_SAMPLE_ROWS = 100_000


def _categorical_histogram(execute: Callable[[Any], pd.DataFrame], expr: Any, col: str,
        length: int = 0) -> list:
    source = expr
    if length > CATEGORICAL_HISTOGRAM_EXACT_MAX_ROWS:
        # ``seed`` is unsupported on the DataFusion backend, so the sample
        # (and the resulting cat_pop estimates) varies run to run. With
        # cache_storage set the first run's snapshot is what gets reused.
        source = expr.sample(CATEGORICAL_HISTOGRAM_SAMPLE_ROWS / length)
    query = (
        source.group_by(col)
        .aggregate(__count=lambda t: t.count())
        .order_by(xo.desc("__count"))
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
            {"name": str(row[col]),
             "cat_pop": round(float(row["__count"]) / total * 100, 1)})
    return out


@stat(default=[])
def histogram(expr: XorqExpr, execute: XorqExecute, orig_col_name: str, is_numeric: bool, is_bool: bool, length: int,
        distinct_count: int, min: float, max: float) -> list:
    """10-bucket numeric histogram or top-10 categorical histogram.

    Numeric columns with very few distinct values (<= 5) fall through to
    the categorical branch — ten quantile buckets over five values is
    mostly empty bars. Mirrors the pd_stats_v2 ``histogram`` threshold.

    ``min`` and ``max`` come from the batch aggregate. The pipeline
    pre-populates them as ``None`` for every column so non-numeric cols
    (where ``min``/``max`` are filtered out by ``column_filter``) don't cascade-
    exclude this stat — the categorical branch ignores them.

    ``distinct_count`` is ``None`` for float columns (the stat is skipped
    there — see ``distinct_count``); floats always take the numeric
    branch, where the <= 5 fallthrough rarely applied anyway.

    All queries go through the injected ``execute`` callable so a
    pipeline-supplied backend isn't bypassed.

    ``default=[]`` provides a graceful fallback if the histogram query
    fails (e.g. backend rejects the GROUP BY). NB: until #687 is fixed,
    the error is silently replaced by ``[]``.
    """
    if length == 0:
        return []
    if is_numeric and not is_bool and (distinct_count is None or distinct_count > 5):
        return _numeric_histogram(execute, expr, orig_col_name, min, max)
    return _categorical_histogram(execute, expr, orig_col_name, length)


@stat(default=[])
def histogram_bins(is_numeric: bool, is_bool: bool, distinct_count: int, min: float, max: float) -> list:
    """Evenly-spaced numeric bin edges consumed by the JS ``color_map`` styler.

    Returns 11 edges (10 equal-width bins) spanning [min, max] — the same
    10-bucket layout used by ``_numeric_histogram``.  Pure computation: only
    depends on ``min`` / ``max`` from the batch aggregate so no extra query
    is needed.

    The JS ``color_map`` rule reads ``histogram_stats[col].histogram_bins``
    to map cell values onto a colour gradient (e.g. DIVERGING_RED_WHITE_BLUE).
    An empty list causes that rule to fall back to ``inherit``, so non-numeric,
    boolean, low-cardinality, and degenerate columns are safely skipped.
    """
    if not is_numeric or is_bool:
        return []
    # distinct_count is None for float columns (stat skipped there) —
    # treat unknown cardinality as high enough to want bins.
    if distinct_count is not None and distinct_count <= 5:
        return []
    if min is None or max is None:
        return []
    if min == max:
        return []
    width = (max - min) / 10
    return [min + i * width for i in range(11)]


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

XORQ_STATS_V2 = [typing_stats, _type, null_count, min, max, distinct_count, mean, std, median,
    non_null_count, nan_per, distinct_per, histogram, histogram_bins]
