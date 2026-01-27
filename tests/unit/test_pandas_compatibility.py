"""
Tests for pandas version compatibility.

These tests ensure buckaroo works correctly across different pandas versions,
particularly catching regressions like the pandas 3.0 to_json(orient='table') issue.
"""
import pandas as pd
import pytest


def test_widget_serialization_pandas_compatibility():
    """
    Test that BuckarooWidget serialization works correctly.

    This is a regression test for pandas 3.0 compatibility. Pandas 3.0 introduced
    a stricter check in DataFrame.to_json(orient='table') that raises ValueError
    when index names overlap with column names. This affected buckaroo's
    _sd_to_jsondf() method in dataflow.py.

    The error was:
        ValueError: Overlapping names between the index and columns
    """
    from buckaroo import BuckarooWidget

    df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie'],
        'age': [25, 30, 35],
        'score': [85.5, 90.0, 78.5]
    })

    # Creating the widget triggers the full serialization pipeline including
    # _sd_to_jsondf() which calls pd.DataFrame(sd).to_json(orient='table')
    widget = BuckarooWidget(df)

    # Verify the widget was created and has data
    assert widget.df_data_dict is not None
    assert 'main' in widget.df_data_dict
    assert 'all_stats' in widget.df_data_dict


def test_polars_widget_serialization_pandas_compatibility():
    """
    Test that PolarsBuckarooWidget serialization works correctly.

    Same regression test as above but for the Polars variant, which also
    uses the pandas serialization path for stats.
    """
    pytest.importorskip('polars')
    import polars as pl
    from buckaroo.polars_buckaroo import PolarsBuckarooWidget

    df = pl.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie'],
        'age': [25, 30, 35],
        'score': [85.5, 90.0, 78.5]
    })

    widget = PolarsBuckarooWidget(df)

    assert widget.df_data_dict is not None
    assert 'main' in widget.df_data_dict
    assert 'all_stats' in widget.df_data_dict


def test_polars_infinite_widget_serialization_pandas_compatibility():
    """
    Test that PolarsBuckarooInfiniteWidget serialization works correctly.

    This was the specific widget that failed in the Playwright Jupyter tests.
    """
    pytest.importorskip('polars')
    import polars as pl
    from buckaroo.polars_buckaroo import PolarsBuckarooInfiniteWidget

    df = pl.DataFrame({
        'row_num': list(range(100)),
        'int_col': [i + 10 for i in range(100)],
        'str_col': [f'foo_{i + 10}' for i in range(100)]
    })

    widget = PolarsBuckarooInfiniteWidget(df)

    assert widget.df_data_dict is not None
    assert 'all_stats' in widget.df_data_dict
