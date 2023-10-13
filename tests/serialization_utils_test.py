import pandas as pd
import numpy as np
from buckaroo.serialization_utils import pd_py_serialize

def test_py_serialize():
    assert pd_py_serialize({'a': pd.NA, 'b': np.nan}) == "{'a': pd.NA, 'b': np.nan, }"
    assert pd_py_serialize({'a': None, 'b': "string", 'c': 4, 'd': 10.3 }) ==\
        "{'a': None, 'b': 'string', 'c': 4, 'd': 10.3, }"
    
