"""Tests for sd_to_parquet_b64 wide-column summary stats serialization.

These verify the Python side of the parquet_b64 transport: encoding
summary stats using one parquet column per (col, stat) pair, with
JSON-encoded cell values.
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

    assert table.num_rows == 1
    col_names = table.column_names
    assert 'a__dtype' in col_names
    assert 'a__mean' in col_names


def test_sd_to_parquet_b64_scalars_round_trip():
    """Scalar values round-trip through JSON encoding in parquet."""
    sd = {
        'col_a': {
            'dtype': 'float64',
            'mean': np.float64(42.0),
            'is_numeric': True,
            'length': 50,
        },
    }
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    # All values are JSON-encoded strings in parquet
    assert json.loads(row['a__mean'][0]) == 42.0
    assert json.loads(row['a__dtype'][0]) == 'float64'
    assert json.loads(row['a__is_numeric'][0]) is True
    assert json.loads(row['a__length'][0]) == 50


def test_sd_to_parquet_b64_histogram_round_trip():
    """Histogram arrays survive the round-trip as JSON strings."""
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

    parsed = json.loads(row['a__histogram'][0])
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

    assert json.loads(row['a__mean'][0]) == 1.0
    assert json.loads(row['b__mean'][0]) == 2.0
    assert json.loads(row['a__dtype'][0]) == 'float64'
    assert json.loads(row['b__dtype'][0]) == 'int64'


def test_sd_to_parquet_b64_nan_encoded():
    """NaN values are JSON-encoded via default=str as 'NaN'."""
    sd = {'col': {'mean': np.nan, 'dtype': 'float64'}}
    result = sd_to_parquet_b64(sd)
    table = _decode_parquet_b64(result)
    row = table.to_pydict()

    # NaN goes through json.dumps(default=str) → "NaN" string
    cell = row['a__mean'][0]
    assert isinstance(cell, str)
    assert json.loads(row['a__dtype'][0]) == 'float64'


def test_sd_to_parquet_b64_value_counts_series():
    """pd.Series values are JSON-encoded via default=str."""
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
