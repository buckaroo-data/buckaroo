import functools
import inspect
import json
import math

import pandas as pd
import polars as pl
import pytest

from buckaroo import ddd_library

def assert_dict_eq(expected, actual):
    expected_keys = sorted(expected.keys())
    actual_keys = sorted(actual.keys())
    assert expected_keys == actual_keys
    for k in actual_keys:
        if not json.dumps(actual[k]) == json.dumps(expected[k]):
            print("FAIL" + "%" * 50)
            print(k)
            print(expected[k])
            print(actual[k])
            assert expected[k] == actual[k]
#            assert (k, expected[k]) == (k, actual[k])


INF = float('inf')
INFINITIES = {'pos': [INF], 'neg': [-INF], 'two_neg': [-INF, -INF], 'both': [-INF, INF],
    'five_each_side': [-INF] * 5 + [INF] * 5}
# np.quantile(col, .01 / .99) is NaN, inf or finite depending on where the tail position falls beside an
# infinity (inf - inf, or inf * 0, inside numpy's interpolation); these finite-value counts straddle that.
FINITE_COUNTS = [6, 7, 20, 49, 50, 98, 99, 100, 101, 102, 150, 200]

# Keys only the categorical histogram's entries carry; a numeric histogram's carry 'population' or 'tail'.
CATEGORICAL_HISTOGRAM_KEYS = {'cat_pop', 'longtail', 'unique'}


def assert_numeric_histogram(histogram, histogram_bins):
    """``histogram`` is numeric buckets, not the categorical fallback, and ``histogram_bins`` is 11 finite edges."""
    keys = {k for entry in histogram for k in entry}
    assert 'population' in keys, f'no numeric buckets: {histogram}'
    assert not keys & CATEGORICAL_HISTOGRAM_KEYS, f'categorical entries: {histogram}'
    assert len(histogram_bins) == 11 and all(math.isfinite(e) for e in histogram_bins), histogram_bins


def _holds_infinity(values) -> bool:
    return any(isinstance(v, float) and math.isinf(v) for v in values)


def _distinct_finite(values) -> int:
    return len({v for v in values if v is not None and math.isfinite(v)})


@functools.lru_cache(maxsize=None)
def _ddd_float_columns_with_infinities() -> tuple:
    columns = []
    for name, fn in inspect.getmembers(ddd_library, inspect.isfunction):
        if fn.__module__ != ddd_library.__name__ or name.startswith('_'):
            continue
        df = fn()
        if isinstance(df, pd.DataFrame) and not isinstance(df.columns, pd.MultiIndex):
            candidates = [(str(col), df.iloc[:, j].tolist()) for j, col in enumerate(df.columns)
                if pd.api.types.is_float_dtype(df.iloc[:, j])]
        elif isinstance(df, pl.DataFrame):
            candidates = [(col, df[col].to_list()) for col in df.columns if df[col].dtype.is_float()]
        else:
            continue
        for col, values in candidates:
            if _holds_infinity(values) and _distinct_finite(values) > 5:
                columns.append((f'{name}-{col}', tuple(values)))
    return tuple(columns)


def ddd_float_columns_with_infinities():
    """A ``pytest.param`` of the values (a tuple, NaN as nan and null as None) of every DDD float column that holds
    an infinity beside more than 5 distinct finite values: enough for a numeric histogram. Frames added to the DDD
    later are picked up."""
    return [pytest.param(values, id=ident) for ident, values in _ddd_float_columns_with_infinities()]
