"""V2 @stat function equivalents for Polars DataFrames.

Mirrors pd_stats_v2.py but uses polars dtype API and series methods.
Functions that operate only on the already-computed stat dict (not the
raw series) are reused from pd_stats_v2 unchanged.

The scalar stats (length, null_count, min, max, distinct_count,
empty_count, mean, std, median) can also come from one ``select`` over the
whole frame, ``pl_prepass_stats``, which polars runs in parallel across
columns. ``PlDfStatsV2`` feeds its result to the pipeline as per-column
``initial_stats``; each per-series stat below whose keys the pre-pass
covers is then dropped from the column's DAG instead of recomputing them,
so the function boundaries here follow the pre-pass groups.

Usage::

    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2

    pipeline = StatPipeline(PL_ANALYSIS_V2)
    result, errors = pipeline.process_df(my_polars_df)
"""
from typing import Any, Dict, Iterable, List, Optional, TypedDict, Union

import numpy as np
import pandas as pd
import polars as pl

from buckaroo.pluggable_analysis_framework.stat_func import stat, RawSeries
from buckaroo.pluggable_analysis_framework.column_filters import is_numeric_not_bool

# Reused unchanged from pd_stats_v2 — operate on stat dict, not raw series
from buckaroo.customizations.pd_stats_v2 import (_type, histogram, cleaning_gen_ops, NumericStatsResult, HistogramSeriesResult)

# value_counts (and mode, most_freq, unique_count, histogram through the
# cascade) are not computed on frames with more rows than this. The
# scalar stats from the pre-pass still are.
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
# Base Summary Stats (polars series API)
# ============================================================

def _pl_vc_to_pd(ser: pl.Series) -> pd.Series:
    """Convert polars value_counts() to a pd.Series sorted desc by count.

    This lets us reuse histogram (and drive pl_freq_stats), which expect
    a pd.Series value_counts.
    """
    vc = ser.drop_nulls().value_counts(sort=True)
    # Cast count to int64 to match the previous .to_list() path's effective
    # dtype. Keeps `categorical_dict`'s `full_long_tail - unique_count`
    # subtraction signed (counts come back as uint32, which underflows on 0-N).
    counts = vc['count'].to_numpy().astype(np.int64, copy=False)
    return pd.Series(counts, index=vc[ser.name].to_numpy())


def _pl_has_min_max(dtype) -> bool:
    """min/max are reported for numeric (non-bool) and temporal columns; other dtypes get nan."""
    return (dtype.is_numeric() and dtype != pl.Boolean) or dtype.is_temporal()


def _pl_is_string_like(dtype) -> bool:
    """Columns whose values can be the empty string."""
    return dtype == pl.String or isinstance(dtype, (pl.Categorical, pl.Enum))


PlScalarResult = TypedDict('PlScalarResult', {'length': int, 'null_count': int, 'min': Any, 'max': Any})


@stat()
def pl_scalar_stats(ser: RawSeries) -> PlScalarResult:
    """Length, null count and min/max for a polars column (pre-pass group)."""
    length = len(ser)
    null_count = int(ser.null_count())
    base = {'length': length, 'null_count': null_count, 'min': float('nan'), 'max': float('nan')}
    if _pl_has_min_max(ser.dtype) and null_count < length:
        base['min'] = ser.min()
        base['max'] = ser.max()
    return base


PlDistinctResult = TypedDict('PlDistinctResult', {'distinct_count': int, 'empty_count': int})


@stat()
def pl_distinct_stats(ser: RawSeries) -> PlDistinctResult:
    """Distinct non-null values and empty-string count (pre-pass group)."""
    non_null = ser.drop_nulls()
    empty_count = 0
    if _pl_is_string_like(ser.dtype):
        empty_count = int((non_null.cast(pl.String) == '').sum())
    # n_unique is not implemented for Object; value_counts is, and it is what the
    # distinct count came from before the pre-pass.
    distinct_count = len(non_null.value_counts()) if ser.dtype == pl.Object else non_null.n_unique()
    return {'distinct_count': int(distinct_count), 'empty_count': empty_count}


PlValueCountsResult = TypedDict('PlValueCountsResult', {'value_counts': pd.Series, 'mode': Any})


@stat(max_rows=VALUE_COUNTS_MAX_ROWS)
def pl_value_counts_stats(ser: RawSeries) -> PlValueCountsResult:
    """value_counts (as a pd.Series, count desc) and mode. The one group-by
    stat in the polars set; gated above VALUE_COUNTS_MAX_ROWS."""
    non_null = ser.drop_nulls()
    return {'value_counts': _pl_vc_to_pd(non_null), 'mode': non_null.mode().item(0) if len(non_null) else None}


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
# Derived stats (from the stat dict, not the raw series)
# ============================================================

PlComputedResult = TypedDict('PlComputedResult',
    {'non_null_count': int, 'distinct_per': float, 'empty_per': float, 'nan_per': float})


@stat()
def pl_computed_summary_stats(length: int, null_count: int, distinct_count: int,
        empty_count: int) -> PlComputedResult:
    """Ratios that need only the scalar stats, so they survive value_counts gating."""
    return {'non_null_count': length - null_count, 'distinct_per': distinct_count / length,
        'empty_per': empty_count / length, 'nan_per': null_count / length}


PlFreqResult = TypedDict('PlFreqResult',
    {'most_freq': Any, '2nd_freq': Any, '3rd_freq': Any, '4th_freq': Any, '5th_freq': Any, 'unique_count': int,
     'unique_per': float})


@stat()
def pl_freq_stats(length: int, value_counts: pd.Series) -> PlFreqResult:
    """Top-5 values and unique (count == 1) stats from value_counts."""
    unique_count = len(value_counts[value_counts == 1])

    def vc_nth(pos):
        if pos >= len(value_counts):
            return None
        return value_counts.index[pos]

    return {'most_freq': vc_nth(0), '2nd_freq': vc_nth(1), '3rd_freq': vc_nth(2), '4th_freq': vc_nth(3),
        '5th_freq': vc_nth(4), 'unique_count': unique_count, 'unique_per': unique_count / length}


# ============================================================
# Pre-pass: the scalar stats for every column in one select
# ============================================================

# Joins column name and stat key in the select's output names.
PREPASS_SEP = '\x1f'
_PREPASS_FLOAT_KEYS = ('mean', 'std', 'median')


def pl_prepass_exprs(schema: pl.Schema, skip_columns: Iterable[str] = (),
        keys: Optional[Iterable[str]] = None) -> List[pl.Expr]:
    """Expressions for the scalar stats of every column, aliased
    ``<column><PREPASS_SEP><stat>``.

    Each column gets the complete key set of the per-series stat the
    values replace (``pl_scalar_stats``, ``pl_distinct_stats``,
    ``pl_numeric_stats``), or none of it, so the pipeline either drops the
    stat for that column or runs it as usual. ``keys`` limits the output
    to those stat keys (None = all of them); the groups are kept whole.
    """
    skip = set(skip_columns)
    wanted = None if keys is None else set(keys)

    def group(*group_keys):
        return wanted is None or all(k in wanted for k in group_keys)

    exprs: List[pl.Expr] = []
    for name, dtype in schema.items():
        if name in skip:
            continue
        c = pl.col(name)

        def a(e, key):
            return e.alias(f'{name}{PREPASS_SEP}{key}')

        if group('length', 'null_count', 'min', 'max'):
            exprs += [a(c.len(), 'length'), a(c.null_count(), 'null_count')]
            if _pl_has_min_max(dtype):
                exprs += [a(c.min(), 'min'), a(c.max(), 'max')]
            else:
                exprs += [a(pl.lit(float('nan')), 'min'), a(pl.lit(float('nan')), 'max')]
        if group('distinct_count', 'empty_count') and dtype != pl.Object:
            exprs.append(a(c.drop_nulls().n_unique(), 'distinct_count'))
            empty = (c.cast(pl.String) == '').sum() if _pl_is_string_like(dtype) else pl.lit(0)
            exprs.append(a(empty, 'empty_count'))
        if group('mean', 'std', 'median') and is_numeric_not_bool(dtype):
            exprs += [a(c.mean(), 'mean'), a(c.std(), 'std'), a(c.median(), 'median')]
    return exprs


def pl_prepass_stats(frame: Union[pl.DataFrame, pl.LazyFrame], skip_columns: Iterable[str] = (),
        keys: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Run the pre-pass select and return ``{column: {stat: value}}``.

    Works on a LazyFrame too, so stats on a scanned file don't need the
    frame in memory. Values match what the per-series stats return: an
    all-null column's min/max/mean/std/median are nan, not None.
    """
    lf = frame.lazy()
    exprs = pl_prepass_exprs(lf.collect_schema(), skip_columns, keys)
    if not exprs:
        return {}
    row = lf.select(exprs).collect().row(0, named=True)
    out: Dict[str, Dict[str, Any]] = {}
    for alias, val in row.items():
        col, key = alias.rsplit(PREPASS_SEP, 1)
        if key in _PREPASS_FLOAT_KEYS:
            val = float(val) if val is not None else float('nan')
        elif val is None and key in ('min', 'max'):
            val = float('nan')
        out.setdefault(col, {})[key] = val
    return out


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

PL_ANALYSIS_V2 = [pl_typing_stats, _type, pl_scalar_stats, pl_distinct_stats, pl_numeric_stats,
    pl_value_counts_stats, pl_computed_summary_stats, pl_freq_stats, pl_histogram_series, histogram]

# Autocleaning analysis set: int-parse detection -> safe_int op.
PL_AUTOCLEAN_DEFAULT_V2 = [pl_cleaning_stats, cleaning_gen_ops]
