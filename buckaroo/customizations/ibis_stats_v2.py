"""Ibis-based analysis classes for the pluggable analysis framework.

Provides IbisAnalysis subclasses that mirror the pandas/polars stat classes
but using ibis expressions. Executed via IbisAnalysisPipeline as a single
batch aggregation query, followed by computed_summary and histogram phases.

Usage::

    from buckaroo.customizations.ibis_stats_v2 import IBIS_ANALYSIS
    from buckaroo.pluggable_analysis_framework.ibis_analysis import IbisAnalysisPipeline

    pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
    stats, errors = pipeline.process_df(ibis_table)
"""
from __future__ import annotations

from typing import Any, List

from buckaroo.pluggable_analysis_framework.ibis_analysis import IbisAnalysis

try:
    import ibis
    HAS_IBIS = True
except ImportError:
    HAS_IBIS = False


# ============================================================
# Expression functions: (table, col) -> ibis.Expr | None
# ============================================================

def _ibis_null_count(table, col):
    return table[col].isnull().sum().cast('int64').name(f"{col}|null_count")


def _ibis_length(table, col):
    return table.count().cast('int64').name(f"{col}|length")


def _ibis_min(table, col):
    if not table.schema()[col].is_numeric():
        return None
    return table[col].min().cast('float64').name(f"{col}|min")


def _ibis_max(table, col):
    if not table.schema()[col].is_numeric():
        return None
    return table[col].max().cast('float64').name(f"{col}|max")


def _ibis_mean(table, col):
    dt = table.schema()[col]
    if not dt.is_numeric() or dt.is_boolean():
        return None
    return table[col].mean().name(f"{col}|mean")


def _ibis_std(table, col):
    dt = table.schema()[col]
    if not dt.is_numeric() or dt.is_boolean():
        return None
    return table[col].std().name(f"{col}|std")


def _ibis_approx_median(table, col):
    dt = table.schema()[col]
    if not dt.is_numeric() or dt.is_boolean():
        return None
    return table[col].approx_median().name(f"{col}|median")


def _ibis_distinct_count(table, col):
    return table[col].nunique().cast('int64').name(f"{col}|distinct_count")


# ============================================================
# IbisAnalysis subclasses
# ============================================================

class IbisTypingStats(IbisAnalysis):
    """Derive type flags from the pre-seeded ibis dtype string.

    No ibis expressions — everything is computed from the schema dtype
    that IbisAnalysisPipeline pre-seeds into column_metadata['dtype'].
    """
    ibis_expressions: List[Any] = []
    provides_defaults = {
        'is_numeric': False,
        'is_integer': False,
        'is_float': False,
        'is_bool': False,
        'is_datetime': False,
        'is_string': False,
        '_type': 'obj',
    }

    @staticmethod
    def computed_summary(column_metadata):
        dt = column_metadata.get('dtype', '')
        is_bool = (dt == 'boolean')
        is_int = any(dt.startswith(p) for p in ('int', 'uint'))
        is_float = any(dt.startswith(p) for p in ('float', 'double', 'decimal'))
        is_numeric = is_int or is_float or is_bool
        is_datetime = any(s in dt for s in ('timestamp', 'date', 'time'))
        is_string = dt in ('string', 'large_string', 'varchar', 'utf8')

        if is_bool:
            _type = 'boolean'
        elif is_int:
            _type = 'integer'
        elif is_float:
            _type = 'float'
        elif is_datetime:
            _type = 'datetime'
        elif is_string:
            _type = 'string'
        else:
            _type = 'obj'

        return {
            'is_numeric': is_numeric,
            'is_integer': is_int,
            'is_float': is_float,
            'is_bool': is_bool,
            'is_datetime': is_datetime,
            'is_string': is_string,
            '_type': _type,
        }


class IbisBaseSummaryStats(IbisAnalysis):
    """Base scalar aggregation stats: null_count, length, min, max, distinct_count."""
    ibis_expressions = [
        _ibis_null_count,
        _ibis_length,
        _ibis_min,
        _ibis_max,
        _ibis_distinct_count,
    ]
    provides_defaults = {
        'null_count': 0,
        'length': 0,
        'min': float('nan'),
        'max': float('nan'),
        'distinct_count': 0,
    }


class IbisNumericStats(IbisAnalysis):
    """Numeric-only stats: mean, std, median.

    Expression functions return None for non-numeric / boolean columns,
    so these stats are only present for numeric columns.
    """
    ibis_expressions = [_ibis_mean, _ibis_std, _ibis_approx_median]
    provides_defaults = {}


class IbisComputedSummaryStats(IbisAnalysis):
    """Derived stats from already-computed keys."""
    ibis_expressions: List[Any] = []
    requires_summary = ['length', 'null_count', 'distinct_count']

    @staticmethod
    def computed_summary(column_metadata):
        length = column_metadata.get('length', 0)
        if not length:
            return {}
        null_count = column_metadata.get('null_count', 0)
        distinct_count = column_metadata.get('distinct_count', 0)
        return {
            'non_null_count': length - null_count,
            'nan_per': null_count / length,
            'distinct_per': distinct_count / length,
        }


# ============================================================
# Histogram support
# ============================================================

def _ibis_histogram_query(table, col, col_stats):
    """Returns an ibis Table expr for the histogram, or None.

    Numeric columns: 10-bucket equal-width histogram between min and max.
    Categorical columns: top-10 by count.
    """
    if not HAS_IBIS:
        return None

    is_numeric = col_stats.get('is_numeric', False)
    is_bool = col_stats.get('is_bool', False)

    if is_numeric and not is_bool:
        min_val = col_stats.get('min')
        max_val = col_stats.get('max')
        if min_val is None or max_val is None:
            return None
        import math
        if math.isnan(min_val) or math.isnan(max_val) or min_val == max_val:
            return None
        bucket = (
            (table[col].cast('float64') - min_val)
            / (max_val - min_val) * 10
        ).cast('int64').clip(lower=0, upper=9)
        return (
            table.mutate(bucket=bucket)
            .group_by('bucket')
            .aggregate(count=lambda t: t.count())
            .order_by('bucket')
        )
    else:
        return (
            table.group_by(col)
            .aggregate(count=lambda t: t.count())
            .order_by(ibis.desc('count'))
            .limit(10)
        )


class IbisHistogramStats(IbisAnalysis):
    """Histogram stats via GROUP BY queries (run after scalar aggregation)."""
    ibis_expressions: List[Any] = []
    histogram_query_fns = [_ibis_histogram_query]
    provides_defaults = {'histogram': []}


# ============================================================
# Convenience list
# ============================================================

IBIS_ANALYSIS = [
    IbisTypingStats,
    IbisBaseSummaryStats,
    IbisNumericStats,
    IbisComputedSummaryStats,
]
