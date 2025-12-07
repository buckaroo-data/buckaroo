"""
Tests for buckaroo.read_utils.read function.
"""
# state:READONLY

import polars as pl
import pytest

from buckaroo.read_utils import read_df


def test_read_df_csv(tmp_path):
    """Test reading CSV files."""
    csv_file = tmp_path / "test.csv"
    df = pl.DataFrame({
        'a': [1, 2, 3],
        'b': ['x', 'y', 'z']
    })
    df.write_csv(csv_file)
    
    ldf = read_df(csv_file)
    assert isinstance(ldf, pl.LazyFrame)
    
    result = ldf.collect()
    assert result.height == 3
    assert result.columns == ['a', 'b']


def test_read_parquet(tmp_path):
    """Test reading Parquet files."""
    parquet_file = tmp_path / "test.parquet"
    df = pl.DataFrame({
        'a': [1, 2, 3],
        'b': ['x', 'y', 'z']
    })
    df.write_parquet(parquet_file)
    
    ldf = read_df(parquet_file)
    assert isinstance(ldf, pl.LazyFrame)
    
    result = ldf.collect()
    assert result.height == 3
    assert result.columns == ['a', 'b']


def test_read_json(tmp_path):
    """Test reading JSON/NDJSON files."""
    json_file = tmp_path / "test.jsonl"
    # Create a simple JSONL file
    with open(json_file, 'w') as f:
        f.write('{"a": 1, "b": "x"}\n')
        f.write('{"a": 2, "b": "y"}\n')
        f.write('{"a": 3, "b": "z"}\n')
    
    ldf = read_df(json_file)
    assert isinstance(ldf, pl.LazyFrame)
    
    result = ldf.collect()
    assert result.height == 3
    assert 'a' in result.columns
    assert 'b' in result.columns


def test_read_nonexistent_file():
    """Test reading a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_df("nonexistent_file.csv")


def test_read_with_string_path(tmp_path):
    """Test that read accepts string paths."""
    csv_file = tmp_path / "test.csv"
    df = pl.DataFrame({'a': [1, 2, 3]})
    df.write_csv(csv_file)
    
    ldf = read_df(str(csv_file))
    assert isinstance(ldf, pl.LazyFrame)
    assert ldf.collect().height == 3


def test_read_extension_detection(tmp_path):
    """Test that read correctly detects file extensions."""
    # Test CSV
    csv_file = tmp_path / "data.CSV"  # uppercase
    df = pl.DataFrame({'a': [1, 2]})
    df.write_csv(csv_file)
    ldf = read_df(csv_file)
    assert isinstance(ldf, pl.LazyFrame)
    
    # Test Parquet
    parquet_file = tmp_path / "data.PARQUET"  # uppercase
    df.write_parquet(parquet_file)
    ldf = read_df(parquet_file)
    assert isinstance(ldf, pl.LazyFrame)
