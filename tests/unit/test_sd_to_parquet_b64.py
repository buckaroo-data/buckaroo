"""Tests for sd_to_parquet_b64 wide-column summary stats serialization.

These verify the Python side of the parquet_b64 transport: encoding
summary stats using one parquet column per (col, stat) pair.
"""
import json
import base64
from io import BytesIO

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from buckaroo.serialization_utils import sd_to_parquet_b64


def _decode_parquet_b64(result):
    """Decode a parquet_b64 payload back to a pyarrow Table."""
    assert isinstance(result, dict)
    assert result['format'] == 'parquet_b64'
    raw = base64.b64decode(result['data'])
    return pq.read_table(BytesIO(raw))


def test_sd_to_parquet_b64_returns_tagged_dict():
    sd = {'col': {'mean': 5.0, 'dtype': 'float64'}}
    result = sd_to_parquet_b64(sd)
    assert result['format'] == 'parquet_b64'
    assert isinstance(result['data'], str)


def test_sd_to_parquet_b64_wide_column_layout():
    """Verify the wide-column layout: one column per (col, stat) pair."""
    sd = {
        'col_a': {
            'dtype': 'float64',
            'mean': np.float64(42.0),
        },
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)

    # Should be single row
    assert table.num_rows == 1

    # Column names should be short_col__stat
    col_names = table.column_names
    assert 'a__dtype' in col_names
    assert 'a__mean' in col_names


def test_sd_to_parquet_b64_scalars_are_native():
    """Scalars should be native parquet types, not JSON strings."""
    sd = {
        'col_a': {
            'dtype': 'float64',
            'mean': np.float64(42.0),
            'min': np.float64(0.0),
            'max': np.float64(100.0),
            'is_numeric': True,
            'length': 50,
        },
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    # Float values are native floats
    assert row['a__mean'] == [42.0]
    assert isinstance(row['a__mean'][0], float)

    # String values are native strings
    assert row['a__dtype'] == ['float64']
    assert isinstance(row['a__dtype'][0], str)

    # Bool values are native bools
    assert row['a__is_numeric'] == [True]
    assert isinstance(row['a__is_numeric'][0], bool)

    # Int values are native ints
    assert row['a__length'] == [50]
    assert isinstance(row['a__length'][0], int)


def test_sd_to_parquet_b64_histogram_is_json_string():
    """Lists/dicts should be JSON-encoded strings in parquet."""
    histogram = [
        {'name': '0.0 - 1.0', 'tail': 1},
        {'name': '1-20', 'population': np.float64(15.0)},
        {'name': '20-40', 'population': np.float64(25.0)},
        {'name': '99.0 - 100.0', 'tail': 1},
    ]
    sd = {
        'col_a': {
            'histogram': histogram,
            'dtype': 'float64',
        },
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    cell = row['a__histogram'][0]
    assert isinstance(cell, str), "histogram should be a JSON string in parquet"

    parsed = json.loads(cell)
    assert isinstance(parsed, list)
    assert len(parsed) == 4
    assert parsed[0] == {'name': '0.0 - 1.0', 'tail': 1}
    assert isinstance(parsed[1]['population'], float)
    assert parsed[1]['population'] == 15.0


def test_sd_to_parquet_b64_categorical_histogram():
    histogram = [
        {'name': 'foo', 'cat_pop': np.float64(40.0)},
        {'name': 'bar', 'cat_pop': np.float64(35.0)},
        {'name': 'longtail', 'longtail': np.float64(15.0)},
        {'name': 'unique', 'unique': np.float64(10.0)},
    ]
    sd = {'col': {'histogram': histogram, 'dtype': 'object'}}
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    parsed = json.loads(row['a__histogram'][0])
    assert parsed[0] == {'name': 'foo', 'cat_pop': 40.0}
    assert isinstance(parsed[0]['cat_pop'], float)
    assert parsed[2] == {'name': 'longtail', 'longtail': 15.0}


def test_sd_to_parquet_b64_multiple_columns():
    sd = {
        'x': {'mean': np.float64(1.0), 'dtype': 'float64'},
        'y': {'mean': np.float64(2.0), 'dtype': 'int64'},
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    assert row['a__mean'] == [1.0]
    assert row['b__mean'] == [2.0]
    assert row['a__dtype'] == ['float64']
    assert row['b__dtype'] == ['int64']


def test_sd_to_parquet_b64_nan_becomes_null():
    """NaN values become null through parquet round-trip."""
    sd = {'col': {'mean': np.nan, 'dtype': 'float64'}}
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    assert row['a__mean'] == [None]
    assert row['a__dtype'] == ['float64']


def test_sd_to_parquet_b64_value_counts_series():
    """pd.Series values should be converted to dicts (JSON-encoded)."""
    sd = {
        'col': {
            'value_counts': pd.Series({'foo': 10, 'bar': 5}),
            'dtype': 'object',
        },
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    cell = row['a__value_counts'][0]
    assert isinstance(cell, str)
    parsed = json.loads(cell)
    assert parsed == {'foo': 10, 'bar': 5}


def test_numpy_scalars_handled_natively_by_pyarrow():
    """pyarrow handles numpy scalars without manual conversion."""
    sd = {
        'col': {
            'mean': np.float64(3.14),
            'count': np.int64(42),
            'is_numeric': np.bool_(True),
            'nan_val': np.nan,
        },
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    assert row['a__mean'] == [3.14]
    assert row['a__count'] == [42]
    assert row['a__is_numeric'] == [True]
    assert row['a__nan_val'] == [None]


