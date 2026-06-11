import pandas as pd
import numpy as np
import polars as pl


from buckaroo.pluggable_analysis_framework.safe_summary_df import pd_py_serialize, output_full_reproduce

def test_py_serialize():
    assert pd_py_serialize({'a': pd.NA, 'b': np.nan}) == "{'a': pd.NA, 'b': np.nan, }"
    assert pd_py_serialize({'a': None, 'b': "string", 'c': 4, 'd': 10.3 }) ==\
        "{'a': None, 'b': 'string', 'c': 4, 'd': 10.3, }"
    assert pd_py_serialize({'a': pl.Series([1,2])}) == "{'a': pl.Series(), }"


def test_output_full_reproduce_handles_errdict():
    """output_full_reproduce prints a line per error without raising; the
    ErrDict is keyed by (col, stat) with a (exception, None) value now that
    the v1 ColAnalysis class is no longer carried."""
    errs = {('a', 'base_summary_stats'): (ZeroDivisionError('division by zero'), None)}
    output_full_reproduce(errs, {'a': {}}, 'testing_df')
