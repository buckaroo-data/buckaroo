"""V2 @stat function equivalents of the v1 ColAnalysis classes.

Provides the same stat keys as the v1 classes, but using the v2
@stat function API with typed DAG dependencies.

Usage::

    from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2

    pipeline = StatPipeline(PD_ANALYSIS_V2)
    result, errors = pipeline.process_df(my_df)

Individual stat groups can also be composed:

    pipeline = StatPipeline([
        typing_stats, _type,
        default_summary_stats,
        computed_default_summary_stats,
        histogram_series, histogram,
    ])
"""
from typing import Any, TypedDict

import numpy as np
import pandas as pd

from buckaroo.pluggable_analysis_framework.stat_func import (
    StatFunc, StatKey, stat, RawSeries,
)

# Helper functions from v1 modules (not rewritten - pure utilities)
from buckaroo.customizations.analysis import get_mode
from buckaroo.customizations.histogram import (
    categorical_histogram, numeric_histogram,
)
from buckaroo.customizations.pd_fracs import (
    regular_int_parse_frac as _regular_int_parse_frac,
    strip_int_parse_frac as _strip_int_parse_frac,
    str_bool_frac as _str_bool_frac,
    us_dates_frac as _us_dates_frac,
)


# ============================================================
# Column metadata
# ============================================================

@stat()
def orig_col_name(ser: RawSeries) -> Any:
    """Provide the original column name as a stat key."""
    return ser.name


# ============================================================
# Typing Stats (replaces TypingStats ColAnalysis)
# ============================================================

TypingResult = TypedDict('TypingResult', {
    'dtype': str,
    'is_numeric': bool,
    'is_integer': bool,
    'is_datetime': bool,
    'is_bool': bool,
    'is_float': bool,
    'is_string': bool,
    'memory_usage': int,
})


@stat()
def typing_stats(ser: RawSeries) -> TypingResult:
    """Compute dtype and type flags for a column."""
    return {
        'dtype': str(ser.dtype),
        'is_numeric': pd.api.types.is_numeric_dtype(ser),
        'is_integer': pd.api.types.is_integer_dtype(ser),
        'is_datetime': pd.api.types.is_datetime64_any_dtype(ser),
        'is_bool': pd.api.types.is_bool_dtype(ser),
        'is_float': pd.api.types.is_float_dtype(ser),
        'is_string': pd.api.types.is_string_dtype(ser),
        'memory_usage': ser.memory_usage(),
    }


@stat()
def _type(is_bool: Any, is_numeric: Any, is_float: Any,
          is_datetime: Any, is_string: Any) -> str:
    """Derive the human-readable column type string."""
    if is_bool:
        return "boolean"
    elif is_numeric:
        if is_float:
            return "float"
        return "integer"
    elif is_datetime:
        return "datetime"
    elif is_string:
        return "string"
    return "obj"


# ============================================================
# Default Summary Stats (replaces DefaultSummaryStats ColAnalysis)
# ============================================================

DefaultSummaryResult = TypedDict('DefaultSummaryResult', {
    'length': int,
    'null_count': int,
    'value_counts': Any,
    'mode': Any,
    'min': Any,
    'max': Any,
    'mean': Any,
    'std': Any,
    'median': Any,
})


@stat()
def default_summary_stats(ser: RawSeries) -> DefaultSummaryResult:
    """Compute basic summary stats for a column."""
    length = len(ser)
    value_counts = ser.value_counts()
    is_numeric = pd.api.types.is_numeric_dtype(ser)
    is_bool = pd.api.types.is_bool_dtype(ser)

    result = {
        'length': length,
        'null_count': ser.isna().sum(),
        'value_counts': value_counts,
        'mode': get_mode(ser),
        'min': np.nan,
        'max': np.nan,
        'mean': 0,
        'std': 0,
        'median': 0,
    }

    if is_numeric and not is_bool and result['null_count'] < length:
        result['std'] = ser.std()
        result['mean'] = ser.mean()
        result['median'] = ser.median()
        result['min'] = ser.dropna().min()
        result['max'] = ser.dropna().max()

    return result


# ============================================================
# Computed Default Summary Stats
# (replaces ComputedDefaultSummaryStats ColAnalysis)
# ============================================================

ComputedSummaryResult = TypedDict('ComputedSummaryResult', {
    'non_null_count': int,
    'most_freq': Any,
    '2nd_freq': Any,
    '3rd_freq': Any,
    '4th_freq': Any,
    '5th_freq': Any,
    'unique_count': int,
    'empty_count': int,
    'distinct_count': int,
    'distinct_per': float,
    'empty_per': float,
    'unique_per': float,
    'nan_per': float,
})


@stat()
def computed_default_summary_stats(
    length: Any, value_counts: Any, null_count: Any,
) -> ComputedSummaryResult:
    """Compute derived stats from basic summary stats."""
    try:
        empty_count = value_counts.get('', 0)
    except Exception:
        empty_count = 0
    distinct_count = len(value_counts)
    unique_count = len(value_counts[value_counts == 1])

    def vc_nth(pos):
        if pos >= len(value_counts):
            return None
        return value_counts.index[pos]

    return {
        'non_null_count': length - null_count,
        'most_freq': vc_nth(0),
        '2nd_freq': vc_nth(1),
        '3rd_freq': vc_nth(2),
        '4th_freq': vc_nth(3),
        '5th_freq': vc_nth(4),
        'unique_count': unique_count,
        'empty_count': empty_count,
        'distinct_count': distinct_count,
        'distinct_per': distinct_count / length,
        'empty_per': empty_count / length,
        'unique_per': unique_count / length,
        'nan_per': null_count / length,
    }


# ============================================================
# Histogram (replaces Histogram ColAnalysis)
# ============================================================

HistogramSeriesResult = TypedDict('HistogramSeriesResult', {
    'histogram_args': Any,
    'histogram_bins': Any,
})


@stat()
def histogram_series(ser: RawSeries) -> HistogramSeriesResult:
    """Compute histogram args from raw series (numeric path)."""
    if not pd.api.types.is_numeric_dtype(ser):
        return {'histogram_args': {}, 'histogram_bins': []}
    if pd.api.types.is_bool_dtype(ser):
        return {'histogram_args': {}, 'histogram_bins': []}
    if not ser.index.is_unique:
        ser = ser.copy()
        ser.index = pd.RangeIndex(len(ser))
    vals = ser.dropna()
    if len(vals) == 0:
        return {'histogram_args': {}, 'histogram_bins': []}
    low_tail = np.quantile(vals, 0.01)
    high_tail = np.quantile(vals, 0.99)
    low_pass = ser > low_tail
    high_pass = ser < high_tail
    meat = vals[low_pass & high_pass]
    if len(meat) == 0:
        return {'histogram_args': {}, 'histogram_bins': []}

    meat_histogram = np.histogram(meat, 10)
    populations, _ = meat_histogram
    return {
        'histogram_bins': meat_histogram[1],
        'histogram_args': dict(
            meat_histogram=meat_histogram,
            normalized_populations=(populations / populations.sum()).tolist(),
            low_tail=low_tail,
            high_tail=high_tail,
        ),
    }


@stat()
def histogram(
    value_counts: Any, nan_per: Any, is_numeric: Any,
    length: Any, min: Any, max: Any,
    histogram_args: Any,
) -> list:
    """Compute histogram from summary stats and histogram args."""
    if is_numeric and len(value_counts) > 5 and histogram_args:
        min_, max_ = min, max
        temp_histo = numeric_histogram(histogram_args, min_, max_, nan_per)
        if len(temp_histo) > 5:
            return temp_histo
    return categorical_histogram(length, value_counts, nan_per)


# ============================================================
# PdCleaningStats (replaces PdCleaningStats ColAnalysis)
# ============================================================

PdCleaningResult = TypedDict('PdCleaningResult', {
    'int_parse_fail': float,
    'int_parse': float,
})


@stat()
def pd_cleaning_stats(value_counts: Any, length: Any) -> PdCleaningResult:
    """Compute int parsing stats for cleaning."""
    vc = value_counts
    coerced_ser = pd.to_numeric(
        vc.index.values, errors='coerce', downcast='integer',
        dtype_backend='pyarrow',
    )
    nan_sum = (pd.Series(coerced_ser).isna() * 1 * vc.values).sum()
    return {
        'int_parse_fail': nan_sum / length,
        'int_parse': (length - nan_sum) / length,
    }


# ============================================================
# Heuristic Fracs (replaces HeuristicFracs ColAnalysis)
# ============================================================

HeuristicFracsResult = TypedDict('HeuristicFracsResult', {
    'str_bool_frac': float,
    'regular_int_parse_frac': float,
    'strip_int_parse_frac': float,
    'us_dates_frac': float,
})


@stat()
def heuristic_fracs(ser: RawSeries) -> HeuristicFracsResult:
    """Compute heuristic parsing fractions for string/object columns."""
    if not (
        pd.api.types.is_string_dtype(ser)
        or pd.api.types.is_object_dtype(ser)
    ):
        return {
            'str_bool_frac': 0,
            'regular_int_parse_frac': 0,
            'strip_int_parse_frac': 0,
            'us_dates_frac': 0,
        }
    return {
        'str_bool_frac': _str_bool_frac(ser),
        'regular_int_parse_frac': _regular_int_parse_frac(ser),
        'strip_int_parse_frac': _strip_int_parse_frac(ser),
        'us_dates_frac': _us_dates_frac(ser),
    }


# ============================================================
# Cleaning Ops (replaces BaseHeuristicCleaningGenOps subclasses)
# ============================================================

try:
    from buckaroo.jlisp.lisp_utils import s, sA
    from buckaroo.auto_clean.heuristic_lang import get_top_score

    def _make_cleaning_stat(rules, rules_op_names, class_name):
        """Factory for heuristic cleaning ops StatFunc objects."""
        def cleaning_func(
            str_bool_frac=0.0, regular_int_parse_frac=0.0,
            strip_int_parse_frac=0.0, us_dates_frac=0.0,
            orig_col_name='',
        ):
            column_metadata = {
                'str_bool_frac': str_bool_frac,
                'regular_int_parse_frac': regular_int_parse_frac,
                'strip_int_parse_frac': strip_int_parse_frac,
                'us_dates_frac': us_dates_frac,
                'orig_col_name': orig_col_name,
            }
            cleaning_op_name = get_top_score(rules, column_metadata)
            if cleaning_op_name == "none":
                return {
                    "cleaning_ops": [],
                    "cleaning_name": "None",
                    "add_orig": False,
                }
            else:
                cleaning_name = rules_op_names.get(
                    cleaning_op_name, cleaning_op_name,
                )
                ops = [
                    sA(
                        cleaning_name,
                        clean_strategy=class_name,
                        clean_col=orig_col_name,
                    ),
                    {"symbol": "df"},
                ]
                return {
                    "cleaning_ops": ops,
                    "cleaning_name": cleaning_name,
                    "add_orig": True,
                }

        cleaning_func.__name__ = class_name
        cleaning_func.__qualname__ = class_name

        return StatFunc(
            name=class_name,
            func=cleaning_func,
            requires=[
                StatKey('str_bool_frac', Any),
                StatKey('regular_int_parse_frac', Any),
                StatKey('strip_int_parse_frac', Any),
                StatKey('us_dates_frac', Any),
                StatKey('orig_col_name', Any),
            ],
            provides=[
                StatKey('cleaning_ops', Any),
                StatKey('cleaning_name', Any),
                StatKey('add_orig', Any),
            ],
            needs_raw=False,
        )

    _frac_name_to_command = {
        "str_bool_frac": "str_bool",
        "regular_int_parse_frac": "regular_int_parse",
        "strip_int_parse_frac": "strip_int_parse",
        "us_dates_frac": "us_date",
    }

    conservative_cleaning = _make_cleaning_stat(
        rules={
            "str_bool_frac": [s("f>"), 0.9],
            "regular_int_parse_frac": [s("f>"), 0.9],
            "strip_int_parse_frac": [s("f>"), 0.9],
            "none": [s("none-rule")],
            "us_dates_frac": [s("primary"), [s("f>"), 0.8]],
        },
        rules_op_names=_frac_name_to_command,
        class_name='ConservativeCleaningGenops',
    )

    aggressive_cleaning = _make_cleaning_stat(
        rules={
            "str_bool_frac": [s("f>"), 0.6],
            "regular_int_parse_frac": [s("f>"), 0.7],
            "strip_int_parse_frac": [s("f>"), 0.6],
            "none": [s("none-rule")],
            "us_dates_frac": [s("primary"), [s("f>"), 0.7]],
        },
        rules_op_names=_frac_name_to_command,
        class_name='AggresiveCleaningGenOps',
    )

except ImportError:
    conservative_cleaning = None
    aggressive_cleaning = None


# ============================================================
# Convenience pipeline lists
# ============================================================

# Core analysis (equivalent to default analysis_klasses)
PD_ANALYSIS_V2 = [
    typing_stats, _type,
    default_summary_stats,
    computed_default_summary_stats,
    histogram_series, histogram,
]

# With cleaning stats
PD_ANALYSIS_V2_WITH_CLEANING = PD_ANALYSIS_V2 + [
    pd_cleaning_stats,
]

# With heuristic fracs (for autocleaning)
PD_ANALYSIS_V2_WITH_HEURISTICS = PD_ANALYSIS_V2 + [
    heuristic_fracs,
    orig_col_name,
]
