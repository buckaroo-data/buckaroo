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

# Reused unchanged from pd_stats_v2 — operate on stat dict, not raw series
from buckaroo.customizations.pd_stats_v2 import (
    _type,
    computed_default_summary_stats,
    histogram,
    BaseSummaryResult,
    NumericStatsResult,
    HistogramSeriesResult,
)


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

PlTypingResult = TypedDict('PlTypingResult', {
    'dtype': str,
    'is_numeric': bool,
    'is_integer': bool,
    'is_float': bool,
    'is_bool': bool,
    'is_datetime': bool,
    'is_string': bool,
    'memory_usage': int,
})


@stat()
def pl_typing_stats(ser: RawSeries) -> PlTypingResult:
    """Compute dtype and type flags for a polars column."""
    dt = ser.dtype
    return {
        'dtype': str(dt),
        'is_numeric': dt.is_numeric(),
        'is_integer': dt.is_integer(),
        'is_float': dt.is_float(),
        'is_bool': dt == pl.Boolean,
        'is_datetime': dt.is_temporal(),
        'is_string': dt in (pl.Utf8, pl.String),
        'memory_usage': ser.estimated_size(),
    }


# ============================================================
# Base Summary Stats (polars series API)
# ============================================================

def _pl_vc_to_pd(ser: pl.Series) -> pd.Series:
    """Convert polars value_counts() to a pd.Series sorted desc by count.

    This lets us reuse computed_default_summary_stats and histogram
    which expect a pd.Series value_counts.
    """
    vc = ser.drop_nulls().value_counts(sort=True)
    col_name = ser.name
    return pd.Series(
        vc['count'].to_list(),
        index=vc[col_name].to_list(),
    )


@stat()
def pl_base_summary_stats(ser: RawSeries) -> BaseSummaryResult:
    """Compute basic summary stats for a polars column."""
    length = len(ser)
    null_count = int(ser.null_count())
    is_numeric = ser.dtype.is_numeric()
    is_bool = ser.dtype == pl.Boolean

    base = {
        'length': length,
        'null_count': null_count,
        'value_counts': _pl_vc_to_pd(ser),
        'mode': ser.drop_nulls().mode().item(0) if null_count < length else None,
        'min': float('nan'),
        'max': float('nan'),
    }

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
    return {
        'mean': float(mean) if mean is not None else float('nan'),
        'std': float(std) if std is not None else float('nan'),
        'median': float(median) if median is not None else float('nan'),
    }


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
    meat_histogram = np.histogram(meat_np, 10)
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
# Convenience pipeline list
# ============================================================

PL_ANALYSIS_V2 = [
    pl_typing_stats, _type,
    pl_base_summary_stats,
    pl_numeric_stats,
    computed_default_summary_stats,
    pl_histogram_series, histogram,
]
