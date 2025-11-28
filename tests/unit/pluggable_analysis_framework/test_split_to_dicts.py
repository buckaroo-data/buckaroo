import json
import polars as pl

from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts


def test_split_to_dicts_json_columns():
    payload = {
        json.dumps(["a", "mean"]): [1.5],
        json.dumps(["b", "null_count"]): [0],
    }
    df = pl.DataFrame(payload)
    out = split_to_dicts(df)
    assert out == {
        "a": {"mean": 1.5},
        "b": {"null_count": 0},
    }


def test_split_to_dicts_suffix_columns():
    df = pl.DataFrame({
        "x|std": [2.0],
        "y|len": [10],
    })
    out = split_to_dicts(df)
    assert out == {
        "x": {"std": 2.0},
        "y": {"len": 10},
    }


def test_split_to_dicts_underscore_fallback():
    df = pl.DataFrame({
        "c_median": [5],
    })
    out = split_to_dicts(df)
    assert out == {
        "c": {"median": 5},
    }


