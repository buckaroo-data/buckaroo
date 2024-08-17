import polars as pl

import json
from collections import defaultdict
from typing import Any, Mapping, MutableMapping, List


def split_to_dicts(stat_df:pl.DataFrame) -> Mapping[str, MutableMapping[str, Any]]:
    summary: MutableMapping[str, MutableMapping[str, Any]] = defaultdict(lambda : {})
    for col in stat_df.columns:
        orig_col, measure = json.loads(col)
        summary[orig_col][measure] = stat_df[col][0]
    return summary


NUMERIC_POLARS_DTYPES:List[pl.DataType] = [
    pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64]
