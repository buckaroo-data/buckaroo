import polars as pl

import json
from collections import defaultdict
from typing import Any, Mapping, MutableMapping, List


def split_to_dicts(stat_df: pl.DataFrame) -> Mapping[str, MutableMapping[str, Any]]:
    """
    Accept stats frames where columns are either:
      - JSON-encoded ["orig_col", "measure"] (legacy format), or
      - Suffix-encoded "orig_col|measure" (no Python callable required).

    Falls back to a last-underscore split "orig_col_measure" if neither applies.
    If no scheme matches, stores the value under a 'value' key for that column.
    """
    summary: MutableMapping[str, MutableMapping[str, Any]] = defaultdict(dict)
    for col in stat_df.columns:
        # Extract single value; default to None for empty frames
        val = stat_df[col][0] if stat_df.height > 0 else None
        orig_col: str
        measure: str

        # Try JSON format first
        parsed = None
        try:
            parsed = json.loads(col)
        except Exception:
            parsed = None

        if isinstance(parsed, list) and len(parsed) == 2:
            orig_col, measure = str(parsed[0]), str(parsed[1])
            summary[orig_col][measure] = val
            continue

        # Try suffix format with a pipe
        if "|" in col:
            orig_col, measure = col.split("|", 1)
            summary[str(orig_col)][str(measure)] = val
            continue

        # Fallback: split on last underscore
        if "_" in col:
            orig_col, measure = col.rsplit("_", 1)
            summary[str(orig_col)][str(measure)] = val
            continue

        # If all else fails, store raw column under a default key
        summary[str(col)]["value"] = val

    return summary


NUMERIC_POLARS_DTYPES:List[pl.DataType] = [
    pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64]
