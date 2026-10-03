"""V2 @stat function equivalents for Polars DataFrames.

Mirrors pd_stats_v2.py but uses polars dtype API and series methods.
Functions that operate only on the already-computed stat dict (not the
raw series) are reused from pd_stats_v2 unchanged.

Usage::

    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2

    pipeline = StatPipeline(PL_ANALYSIS_V2)
    result, errors = pipeline.process_df(my_polars_df)
"""
from typing import Any, TypedDict

import numpy as np
import pandas as pd
import polars as pl

from buckaroo.pluggable_analysis_framework.stat_func import stat, RawSeries
from buckaroo.pluggable_analysis_framework.column_filters import is_numeric_not_bool
from buckaroo.pluggable_analysis_framework.polars_utils import vc_frame_to_pd

# Reused unchanged from pd_stats_v2 — operate on stat dict, not raw series
from buckaroo.customizations.pd_stats_v2 import (_type, computed_default_summary_stats, histogram, cleaning_gen_ops, NumericStatsResult, HistogramSeriesResult)


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
# Base Summary Stats (polars series API)
# ============================================================

def _pl_vc_to_pd(ser: pl.Series) -> pd.Series:
    """Convert polars value_counts() to a pd.Series sorted desc by count.

    This lets us reuse computed_default_summary_stats and histogram
    which expect a pd.Series value_counts.
    """
    return vc_frame_to_pd(ser.drop_nulls().value_counts(sort=True), ser.name)


PlValueCountsResult = TypedDict('PlValueCountsResult', {'value_counts': pd.Series})


@stat()
def pl_value_counts(ser: RawSeries) -> PlValueCountsResult:
    """value_counts of one polars column, per Series.

    ``PlDfStatsV2`` computes the same thing for every column in one batch
    (``polars_utils.batch_value_counts``) and seeds it into the accumulator,
    in which case this stat is skipped.
    """
    return {'value_counts': _pl_vc_to_pd(ser)}


PlBaseSummaryResult = TypedDict('PlBaseSummaryResult',
    {'length': int, 'null_count': int, 'mode': Any, 'min': Any, 'max': Any})


def _mode_from_value_counts(value_counts: pd.Series) -> Any:
    """First row of value_counts; numpy scalars become Python scalars so the
    result matches what ``Series.mode().item(0)`` returned."""
    if len(value_counts) == 0:
        return None
    top = value_counts.index[0]
    return top.item() if isinstance(top, np.generic) else top


@stat()
def pl_base_summary_stats(ser: RawSeries, value_counts: pd.Series) -> PlBaseSummaryResult:
    """Compute basic summary stats for a polars column.

    ``mode`` is the first row of ``value_counts`` rather than a second
    group-by over the column (#997). Which of several tied values wins was
    unspecified before and still is.
    """
    length = len(ser)
    null_count = int(ser.null_count())
    is_numeric = ser.dtype.is_numeric()
    is_bool = ser.dtype == pl.Boolean

    base = {'length': length, 'null_count': null_count, 'mode': _mode_from_value_counts(value_counts),
        'min': float('nan'), 'max': float('nan')}

    if is_numeric and not is_bool and null_count < length:
        non_null = ser.drop_nulls()
        base['min'] = non_null.min()
        base['max'] = non_null.max()

    return base


# ============================================================
# Numeric Stats (mean/std/median — numeric non-bool only)
# ============================================================

@stat(column_filter=is_numeric_not_bool)
def pl_numeric_stats(ser: RawSeries) -> NumericStatsResult:
    """Compute mean/std/median for numeric non-bool polars columns."""
    mean = ser.mean()
    std = ser.std()
    median = ser.median()
    return {'mean': float(mean) if mean is not None else float('nan'),
        'std': float(std) if std is not None else float('nan'),
        'median': float(median) if median is not None else float('nan')}


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

PL_ANALYSIS_V2 = [pl_typing_stats, _type, pl_value_counts, pl_base_summary_stats, pl_numeric_stats,
    computed_default_summary_stats, pl_histogram_series, histogram]

# Autocleaning analysis set: int-parse detection -> safe_int op.
PL_AUTOCLEAN_DEFAULT_V2 = [pl_cleaning_stats, cleaning_gen_ops]
