"""V2 @stat function equivalents for Polars DataFrames.

Mirrors pd_stats_v2.py. Stats that are one aggregation take a ``PlColumn``
and return a ``pl.Expr``; ``PolarsStatPipeline`` runs all of them, for
every column, in a single select over the frame (#999). Stats that need
the series (typing, value_counts, the histogram bins) take a ``RawSeries``.
Functions that operate only on the already-computed stat dict are reused
from pd_stats_v2 where the keys line up.

Usage::

    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
    from buckaroo.pluggable_analysis_framework.polars_stat_pipeline import PolarsStatPipeline

    pipeline = PolarsStatPipeline(PL_ANALYSIS_V2)
    result, errors = pipeline.process_df(my_polars_df)
"""
from typing import Any, TypedDict

import numpy as np
import pandas as pd
import polars as pl

from buckaroo.pluggable_analysis_framework.stat_func import stat, RawSeries, PlColumn
from buckaroo.pluggable_analysis_framework.column_filters import is_numeric_not_bool

# Reused unchanged from pd_stats_v2 — operate on stat dict, not raw series
from buckaroo.customizations.pd_stats_v2 import (_type, histogram, cleaning_gen_ops, HistogramSeriesResult)

# value_counts is a group-by on every column; above this many rows it is
# skipped (and mode, the *_freq keys and histogram with it) rather than
# spending the seconds #999 measured. The batch stats still run.
VALUE_COUNTS_MAX_ROWS = 10_000_000


# ============================================================
# Column metadata
# ============================================================

@stat()
def pl_orig_col_name(ser: RawSeries) -> Any:
    """Provide the original column name as a stat key."""
    return ser.name


# ============================================================
# Typing Stats (polars dtype API)
# ============================================================

PlTypingResult = TypedDict('PlTypingResult',
    {'dtype': str, 'is_numeric': bool, 'is_integer': bool, 'is_float': bool, 'is_bool': bool, 'is_datetime': bool,
     'is_timedelta': bool, 'is_string': bool, 'is_categorical': bool, 'is_period': bool, 'is_interval': bool,
     'is_time': bool, 'is_decimal': bool, 'is_binary': bool, 'memory_usage': int})


@stat()
def pl_typing_stats(ser: RawSeries) -> PlTypingResult:
    """Compute dtype and type flags for a polars column."""
    dt = ser.dtype
    return {'dtype': str(dt), 'is_numeric': dt.is_numeric() and dt.base_type() is not pl.Decimal,
        'is_integer': dt.is_integer(), 'is_float': dt.is_float(), 'is_bool': dt == pl.Boolean,
        'is_datetime': dt.is_temporal() and dt not in (pl.Duration, pl.Time), 'is_timedelta': dt == pl.Duration,
        'is_string': dt in (pl.Utf8, pl.String), 'is_categorical': dt == pl.Categorical or isinstance(dt, pl.Enum),
        'is_period': False, 'is_interval': False, 'is_time': dt == pl.Time, 'is_decimal': dt.base_type() is pl.Decimal,
        'is_binary': dt == pl.Binary, 'memory_usage': ser.estimated_size()}


# ============================================================
# Batched aggregates — one pl.Expr each, folded into the batch select
# ============================================================
# These functions return ``pl.Expr`` at runtime; PolarsStatPipeline folds
# them into one ``select`` and the resulting scalar lands in the accumulator
# under the key matching the function name. Type annotations describe the
# eventual scalar type in the accumulator.
#
# Names like ``min`` / ``max`` shadow the corresponding builtins inside this
# module — intentional, as in xorq_stats_v2. Module-internal code never
# calls ``builtins.min`` / ``max``.


def _is_pl_numeric_not_bool(dtype) -> bool:
    # polars' own predicate (includes Decimal) for min/max, as the series
    # path did; mean/std/median use the shared is_numeric_not_bool filter.
    return dtype.is_numeric() and dtype != pl.Boolean


@stat()
def length(col: PlColumn) -> int:
    return col.expr.len()


@stat()
def null_count(col: PlColumn) -> int:
    return col.expr.null_count()


@stat()
def distinct_count(col: PlColumn) -> int:
    """Exact count of distinct non-null values."""
    return col.expr.drop_nulls().n_unique()


@stat()
def min(col: PlColumn) -> Any:
    """Smallest non-null value of a numeric column; NaN for other dtypes."""
    if _is_pl_numeric_not_bool(col.dtype):
        return col.expr.min()
    return pl.lit(float('nan'))


@stat()
def max(col: PlColumn) -> Any:
    """Largest non-null value of a numeric column; NaN for other dtypes."""
    if _is_pl_numeric_not_bool(col.dtype):
        return col.expr.max()
    return pl.lit(float('nan'))


@stat(column_filter=is_numeric_not_bool)
def mean(col: PlColumn) -> float:
    return col.expr.mean().fill_null(float('nan'))


@stat(column_filter=is_numeric_not_bool)
def std(col: PlColumn) -> float:
    return col.expr.std().fill_null(float('nan'))


@stat(column_filter=is_numeric_not_bool)
def median(col: PlColumn) -> float:
    return col.expr.median().fill_null(float('nan'))


# ============================================================
# value_counts and the stats derived from it (per series, row-gated)
# ============================================================

def _pl_vc_to_pd(ser: pl.Series) -> pd.Series:
    """Non-null value counts as a pd.Series sorted by count desc, then value asc.

    This lets us reuse histogram, which expects a pd.Series value_counts.
    The value tie-break makes ``mode`` / ``most_freq`` deterministic; polars'
    own order among tied counts depends on the plan.
    """
    vc = ser.drop_nulls().value_counts()
    try:
        vc = vc.sort(['count', ser.name], descending=[True, False])
    except Exception:
        # dtypes polars can't order (nested, object): count order only
        vc = vc.sort('count', descending=True)
    # Cast count to int64 to match the previous .to_list() path's effective
    # dtype. Keeps `categorical_dict`'s `full_long_tail - unique_count`
    # subtraction signed (counts come back as uint32, which underflows on 0-N).
    counts = vc['count'].to_numpy().astype(np.int64, copy=False)
    return pd.Series(counts, index=vc[ser.name].to_numpy())


@stat(max_rows=VALUE_COUNTS_MAX_ROWS)
def value_counts(ser: RawSeries) -> pd.Series:
    """Non-null value counts, sorted by count desc then value asc."""
    return _pl_vc_to_pd(ser)


@stat()
def mode(value_counts: pd.Series) -> Any:
    """Most frequent non-null value, None when every value is null. Ties go
    to the smallest value, by value_counts' order."""
    if len(value_counts) == 0:
        return None
    val = value_counts.index[0]
    if isinstance(val, (np.integer, np.floating, np.bool_)):
        return val.item()
    return val


PlRatioResult = TypedDict('PlRatioResult', {'non_null_count': int, 'nan_per': float, 'distinct_per': float})


@stat()
def pl_ratio_stats(length: int, null_count: int, distinct_count: int) -> PlRatioResult:
    """Ratios that only need batch scalars, so they survive when value_counts
    is gated."""
    return {'non_null_count': length - null_count, 'nan_per': null_count / length,
        'distinct_per': distinct_count / length}


PlFreqResult = TypedDict('PlFreqResult',
    {'most_freq': Any, '2nd_freq': Any, '3rd_freq': Any, '4th_freq': Any, '5th_freq': Any, 'unique_count': int,
     'empty_count': int, 'empty_per': float, 'unique_per': float})


@stat()
def pl_freq_stats(length: int, value_counts: pd.Series) -> PlFreqResult:
    """The value_counts-derived keys of computed_default_summary_stats."""
    try:
        empty_count = value_counts.get('', 0)
    except Exception:
        empty_count = 0
    unique_count = len(value_counts[value_counts == 1])

    def vc_nth(pos):
        if pos >= len(value_counts):
            return None
        return value_counts.index[pos]

    return {'most_freq': vc_nth(0), '2nd_freq': vc_nth(1), '3rd_freq': vc_nth(2), '4th_freq': vc_nth(3),
        '5th_freq': vc_nth(4), 'unique_count': unique_count, 'empty_count': empty_count,
        'empty_per': empty_count / length, 'unique_per': unique_count / length}


# ============================================================
# Histogram Series (polars series API)
# ============================================================

@stat()
def pl_histogram_series(ser: RawSeries) -> HistogramSeriesResult:
    """Compute histogram args from raw polars series (numeric path)."""
    if not ser.dtype.is_numeric():
        return {'histogram_args': {}, 'histogram_bins': []}
    if ser.dtype == pl.Boolean:
        return {'histogram_args': {}, 'histogram_bins': []}

    vals = ser.drop_nulls()
    if len(vals) == 0:
        return {'histogram_args': {}, 'histogram_bins': []}

    low_tail = vals.quantile(0.01)
    high_tail = vals.quantile(0.99)
    low_pass = vals > low_tail
    high_pass = vals < high_tail
    meat = vals.filter(low_pass & high_pass)
    if len(meat) == 0:
        return {'histogram_args': {}, 'histogram_bins': []}

    meat_np = meat.to_numpy()
    try:
        meat_histogram = np.histogram(meat_np, 10)
    except ValueError:
        # Can happen when float64 precision is insufficient to create
        # 10 distinct bin edges (e.g. large integers near 2^53 where
        # np.spacing > bin width).
        return {'histogram_args': {}, 'histogram_bins': []}
    populations, _ = meat_histogram
    return {
        'histogram_bins': meat_histogram[1].tolist(),
        'histogram_args': dict(
            meat_histogram=meat_histogram,
            normalized_populations=(populations / populations.sum()).tolist(),
            low_tail=low_tail,
            high_tail=high_tail,
        ),
    }


# ============================================================
# Cleaning stats (int-parse detection for autocleaning)
# ============================================================

PlCleaningResult = TypedDict('PlCleaningResult', {'int_parse_fail': float, 'int_parse': float})


@stat()
def pl_cleaning_stats(ser: RawSeries) -> PlCleaningResult:
    """Fraction of a polars column that parses as int (drives safe_int autoclean)."""
    length = len(ser)
    if length == 0:
        return {'int_parse_fail': 0.0, 'int_parse': 0.0}
    parsed = ser.cast(pl.Int64, strict=False)
    ok = int(parsed.is_not_null().sum())
    return {'int_parse': ok / length, 'int_parse_fail': (length - ok) / length}


# ============================================================
# Convenience pipeline lists
# ============================================================

# The keys pl_base_summary_stats used to provide in one function.
PL_BASE_SUMMARY_STATS = [length, null_count, distinct_count, min, max, value_counts, mode]
PL_NUMERIC_STATS = [mean, std, median]

PL_ANALYSIS_V2 = [pl_typing_stats, _type] + PL_BASE_SUMMARY_STATS + PL_NUMERIC_STATS + [pl_ratio_stats,
    pl_freq_stats, pl_histogram_series, histogram]

# Autocleaning analysis set: int-parse detection -> safe_int op.
PL_AUTOCLEAN_DEFAULT_V2 = [pl_cleaning_stats, cleaning_gen_ops]
