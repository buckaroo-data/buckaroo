"""Tests for the lossless summary-dict codec used by the initial-load cache.

serialize_sd / deserialize_sd persist a ``merged_sd`` losslessly to parquet
without pickle, dropping ``value_counts`` (never recomputed from, never read by
the frontend). The value types differ per backend (pandas → pd.Timestamp;
polars → stdlib datetime / Decimal / bytes; xorq → mixed), so the codec must
round-trip the full union. See docs/initial-load-cache-design.md.
"""
import datetime
import decimal
import math

import numpy as np
import pandas as pd

from buckaroo.cache.sd_codec import serialize_sd, deserialize_sd


def test_roundtrip_value_types():
    sd = {
        'a': {
            '_type': 'integer', 'dtype': 'int64',
            'min': np.int64(3), 'max': 10,
            'mean': np.float64(5.5),
            'nan_stat': float('nan'),
            'np_nan': np.float64('nan'),
            'flag': np.bool_(True), 'py_flag': False,
            'ts': pd.Timestamp('2020-01-02T03:04:05'),
            'td': pd.Timedelta(days=2, hours=3),
            'pydt': datetime.datetime(2021, 1, 1, 12, 30, 0),
            'pydate': datetime.date(2021, 1, 1),
            'pytime': datetime.time(13, 30, 15),
            'pytd': datetime.timedelta(hours=5, minutes=10),
            'dec': decimal.Decimal('3.14'),
            'blob': b'\x00\x01hello',
            'histogram': [{'name': '0-5', 'population': np.float64(40.0)},
                          {'name': 'NA', 'NA': 2.0}],
            'orig_col_name': 'A',
            'value_counts': pd.Series([1, 2, 3]),  # must be DROPPED
        },
        'b': {'_type': 'string', 'dtype': 'object', 'orig_col_name': 'B'},
    }
    out = deserialize_sd(serialize_sd(sd))

    assert set(out.keys()) == {'a', 'b'}
    a = out['a']
    assert 'value_counts' not in a
    assert a['_type'] == 'integer' and a['dtype'] == 'int64'
    assert a['min'] == 3 and a['max'] == 10
    assert a['mean'] == 5.5
    assert math.isnan(a['nan_stat']) and math.isnan(a['np_nan'])
    assert a['flag'] is True and a['py_flag'] is False
    assert a['ts'] == pd.Timestamp('2020-01-02T03:04:05')
    assert a['td'] == pd.Timedelta(days=2, hours=3)
    assert a['pydt'] == datetime.datetime(2021, 1, 1, 12, 30, 0)
    assert a['pydate'] == datetime.date(2021, 1, 1)
    assert a['pytime'] == datetime.time(13, 30, 15)
    assert a['pytd'] == datetime.timedelta(hours=5, minutes=10)
    assert a['dec'] == decimal.Decimal('3.14')
    assert a['blob'] == b'\x00\x01hello'
    assert a['histogram'] == [{'name': '0-5', 'population': 40.0}, {'name': 'NA', 'NA': 2.0}]
    assert a['orig_col_name'] == 'A'
    assert out['b']['orig_col_name'] == 'B'


def test_orig_col_name_tuple_roundtrips():
    # MultiIndex columns carry orig_col_name as a tuple — must not degrade to a list.
    sd = {'a': {'_type': 'float', 'orig_col_name': ('lvl1', 'lvl2')}}
    out = deserialize_sd(serialize_sd(sd))
    assert out['a']['orig_col_name'] == ('lvl1', 'lvl2')


def test_returns_bytes_and_empty_ok():
    assert isinstance(serialize_sd({}), bytes)
    assert deserialize_sd(serialize_sd({})) == {}


def test_roundtrip_real_pandas_pipeline_sd():
    from buckaroo.customizations.analysis import (
        TypingStats, DefaultSummaryStats, ComputedDefaultSummaryStats)
    from buckaroo.customizations.histogram import Histogram
    from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2

    df = pd.DataFrame({'ints': [1, 2, 3, None], 'floats': [1.5, 2.5, 3.5, 4.5], 'strs': ['a', 'b', 'c', 'd'],
        'dates': pd.to_datetime(['2020-01-01', '2020-06-01', '2021-01-01', '2021-06-01'])})
    sd = DfStatsV2(
        df, [TypingStats, DefaultSummaryStats, Histogram, ComputedDefaultSummaryStats],
        'test_df').sdf
    out = deserialize_sd(serialize_sd(sd))
    # Every non-value_counts stat key survives the round-trip, per column.
    assert set(out.keys()) == set(sd.keys())
    for col, meta in sd.items():
        for k in meta:
            if k == 'value_counts':
                continue
            assert k in out[col], f"{col}.{k} lost in round-trip"
