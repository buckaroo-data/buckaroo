import pandas as pd
import numpy as np
import polars as pl


from buckaroo.pluggable_analysis_framework.safe_summary_df import pd_py_serialize

def test_py_serialize():
    assert pd_py_serialize({'a': pd.NA, 'b': np.nan}) == "{'a': pd.NA, 'b': np.nan, }"
    assert pd_py_serialize({'a': None, 'b': "string", 'c': 4, 'd': 10.3 }) ==\
        "{'a': None, 'b': 'string', 'c': 4, 'd': 10.3, }"
    assert pd_py_serialize({'a': pl.Series([1,2])}) == "{'a': pl.Series(), }"
