"""Tests for sd_to_parquet_b64 summary stats serialization.

These verify the Python side of the parquet_b64 transport: encoding
summary stats (including histograms) to parquet and verifying the
round-trip through pyarrow produces correct data that the JS side's
resolveDFData/JSON.parse can consume.
"""
import json
import base64
from io import BytesIO

import numpy as np
import pyarrow.parquet as pq

from buckaroo.serialization_utils import sd_to_parquet_b64


def _decode_parquet_b64(result):
    """Decode a parquet_b64 payload back to a DataFrame."""
    assert isinstance(result, dict)
    assert result['format'] == 'parquet_b64'
    raw = base64.b64decode(result['data'])
    return pq.read_table(BytesIO(raw)).to_pandas()


def test_sd_to_parquet_b64_returns_tagged_dict():
    sd = {'col': {'mean': 5.0, 'dtype': 'float64'}}
    result = sd_to_parquet_b64(sd)
    assert result['format'] == 'parquet_b64'
    assert isinstance(result['data'], str)


def test_sd_to_parquet_b64_round_trip_scalars():
    sd = {'col_a': {'dtype': 'float64', 'mean': np.float64(42.0), 'min': np.float64(0.0), 'max': np.float64(100.0)}}
    result = sd_to_parquet_b64(sd)
    df = _decode_parquet_b64(result)

    # Find the mean row and verify the value round-trips
    mean_row = df[df['index'] == 'mean']
    assert len(mean_row) == 1
    cell = mean_row.iloc[0]['a']  # column 'col_a' becomes 'a'
    assert json.loads(cell) == 42.0


def test_sd_to_parquet_b64_histogram_round_trip():
    """Verify histogram arrays survive the parquet_b64 round-trip.

    This is the key test for #630: histogram data must be JSON-decodable
    from the parquet payload with correct types (numbers, not strings).
    """
    histogram = [
        {'name': '0.0 - 1.0', 'tail': 1},
        {'name': '1-20', 'population': np.float64(15.0)},
        {'name': '20-40', 'population': np.float64(25.0)},
        {'name': '99.0 - 100.0', 'tail': 1}]
    sd = {'col_a': {'histogram': histogram, 'dtype': 'float64'}}
    result = sd_to_parquet_b64(sd)
    df = _decode_parquet_b64(result)

    hist_row = df[df['index'] == 'histogram']
    assert len(hist_row) == 1

    cell = hist_row.iloc[0]['a']
    assert isinstance(cell, str), "histogram cell should be a JSON string in parquet"

    parsed = json.loads(cell)
    assert isinstance(parsed, list), "histogram should parse as a list"
    assert len(parsed) == 4

    # Verify types: numbers must be numbers, not strings
    assert parsed[0] == {'name': '0.0 - 1.0', 'tail': 1}
    assert isinstance(parsed[0]['tail'], int)

    assert parsed[1]['name'] == '1-20'
    assert isinstance(parsed[1]['population'], float)
    assert parsed[1]['population'] == 15.0


def test_sd_to_parquet_b64_categorical_histogram():
    histogram = [
        {'name': 'foo', 'cat_pop': np.float64(40.0)},
        {'name': 'bar', 'cat_pop': np.float64(35.0)},
        {'name': 'longtail', 'longtail': np.float64(15.0)},
        {'name': 'unique', 'unique': np.float64(10.0)}]
    sd = {'col': {'histogram': histogram, 'dtype': 'object'}}
    result = sd_to_parquet_b64(sd)
    df = _decode_parquet_b64(result)

    hist_row = df[df['index'] == 'histogram']
    parsed = json.loads(hist_row.iloc[0]['a'])

    assert parsed[0] == {'name': 'foo', 'cat_pop': 40.0}
    assert isinstance(parsed[0]['cat_pop'], float)
    assert parsed[2] == {'name': 'longtail', 'longtail': 15.0}


def test_sd_to_parquet_b64_multiple_columns():
    sd = {'x': {'mean': np.float64(1.0), 'dtype': 'float64'}, 'y': {'mean': np.float64(2.0), 'dtype': 'int64'}}
    result = sd_to_parquet_b64(sd)
    df = _decode_parquet_b64(result)

    # Columns are rewritten to 'a', 'b' by prepare_df_for_serialization
    mean_row = df[df['index'] == 'mean']
    assert json.loads(mean_row.iloc[0]['a']) == 1.0
    assert json.loads(mean_row.iloc[0]['b']) == 2.0
