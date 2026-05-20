"""Tests for sd_to_parquet_b64 summary stats serialization.

The wide-typed layout writes one parquet column per ``{short_col}__{stat_name}``
with native parquet types for numeric and bool scalars. Strings and list/dict
values still go through JSON so the JS side can JSON.parse every string cell
unambiguously.
"""
import base64
import json
import math
from io import BytesIO

import numpy as np
import pyarrow.parquet as pq

from buckaroo.serialization_utils import sd_to_parquet_b64


def _decode(result):
    assert isinstance(result, dict)
    assert result['format'] == 'parquet_b64'
    assert result.get('layout') == 'wide'
    raw = base64.b64decode(result['data'])
    return pq.read_table(BytesIO(raw))


def test_tagged_payload_carries_wide_layout():
    sd = {'col': {'mean': 5.0, 'dtype': 'float64'}}
    result = sd_to_parquet_b64(sd)
    assert result['format'] == 'parquet_b64'
    assert result['layout'] == 'wide'
    assert isinstance(result['data'], str)


def test_numeric_scalars_use_native_parquet_types():
    """The headline win: floats are float64, ints are int64, bools are bool.

    No JSON round-trip for numeric values — they ride the parquet schema.
    """
    sd = {'col_a': {'mean': np.float64(42.0), 'length': 50, 'is_numeric': True, 'dtype': 'float64'}}
    table = _decode(sd_to_parquet_b64(sd))
    schema = {f.name: str(f.type) for f in table.schema}
    assert schema['a__mean'] == 'double'
    assert schema['a__length'] == 'int64'
    assert schema['a__is_numeric'] == 'bool'
    assert schema['a__dtype'] == 'string'  # strings stay JSON-encoded


def test_native_scalars_round_trip_without_json():
    sd = {'col_a': {'mean': np.float64(42.5), 'length': 50, 'is_numeric': True}}
    table = _decode(sd_to_parquet_b64(sd))
    row = table.to_pydict()
    # Values come out as native Python types — not JSON strings.
    assert row['a__mean'] == [42.5]
    assert row['a__length'] == [50]
    assert row['a__is_numeric'] == [True]


def test_string_values_remain_json_encoded():
    """Strings are JSON-encoded so the JS side can parse every string cell
    without needing to know which columns hold raw strings vs JSON lists.

    A plain ``"float64"`` round-trips as the JSON literal ``'"float64"'``.
    """
    sd = {'col_a': {'dtype': 'float64'}}
    table = _decode(sd_to_parquet_b64(sd))
    raw_cell = table.to_pydict()['a__dtype'][0]
    assert raw_cell == '"float64"'
    assert json.loads(raw_cell) == 'float64'


def test_histogram_round_trips_as_json_string():
    histogram = [{'name': '0-20', 'population': np.float64(15.0)}, {'name': '20-40', 'population': np.float64(25.0)}]
    sd = {'col_a': {'histogram': histogram, 'dtype': 'float64'}}
    table = _decode(sd_to_parquet_b64(sd))
    raw_cell = table.to_pydict()['a__histogram'][0]
    assert isinstance(raw_cell, str)
    parsed = json.loads(raw_cell)
    assert parsed[0]['name'] == '0-20'
    assert parsed[0]['population'] == 15.0
    assert isinstance(parsed[0]['population'], float)


def test_nan_becomes_parquet_null():
    """NaN floats serialize as parquet null (not the string 'NaN').

    On the JS side this surfaces as ``null``, which is what consumers expect
    for "no value" stats like mean of an all-NaN column.
    """
    sd = {'col_a': {'mean': math.nan, 'dtype': 'float64'}}
    table = _decode(sd_to_parquet_b64(sd))
    row = table.to_pydict()
    assert row['a__mean'] == [None]


def test_none_serializes_as_null():
    sd = {'col_a': {'mean': None, 'dtype': 'float64'}}
    table = _decode(sd_to_parquet_b64(sd))
    row = table.to_pydict()
    assert row['a__mean'] == [None]


def test_multiple_columns_get_short_name_prefix():
    """Column names follow the to_chars() rename: first col is 'a', second 'b'."""
    sd = {'x': {'mean': np.float64(1.0), 'dtype': 'float64'}, 'y': {'mean': np.float64(2.0), 'dtype': 'int64'}}
    table = _decode(sd_to_parquet_b64(sd))
    row = table.to_pydict()
    assert row['a__mean'] == [1.0]
    assert row['b__mean'] == [2.0]
    assert json.loads(row['a__dtype'][0]) == 'float64'
    assert json.loads(row['b__dtype'][0]) == 'int64'


def test_categorical_histogram_round_trips():
    histogram = [{'name': 'foo', 'cat_pop': np.float64(40.0)}, {'name': 'bar', 'cat_pop': np.float64(35.0)},
        {'name': 'longtail', 'longtail': np.float64(15.0)}, {'name': 'unique', 'unique': np.float64(10.0)}]
    sd = {'col': {'histogram': histogram, 'dtype': 'object'}}
    table = _decode(sd_to_parquet_b64(sd))
    parsed = json.loads(table.to_pydict()['a__histogram'][0])
    assert parsed[0] == {'name': 'foo', 'cat_pop': 40.0}
    assert isinstance(parsed[0]['cat_pop'], float)
    assert parsed[2] == {'name': 'longtail', 'longtail': 15.0}


def test_single_row_layout():
    """Wide layout writes exactly one row regardless of stat count."""
    sd = {'col_a': {'mean': 1.0, 'min': 0.0, 'max': 2.0, 'dtype': 'float64'}}
    table = _decode(sd_to_parquet_b64(sd))
    assert table.num_rows == 1


def test_empty_sd_round_trips():
    """An empty SD (no columns) produces a valid empty-schema payload."""
    result = sd_to_parquet_b64({})
    assert result['format'] == 'parquet_b64'
    assert result['layout'] == 'wide'
    table = _decode(result)
    assert table.num_columns == 0
