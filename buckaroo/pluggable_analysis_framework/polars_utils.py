import polars as pl

import json
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, MutableMapping, List, Optional

import numpy as np
import pandas as pd


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


def vc_frame_to_pd(vc: pl.DataFrame, name: str) -> pd.Series:
    """Convert a polars value_counts frame (columns ``name``, ``count``) to a
    pd.Series of counts indexed by value, in the frame's row order.

    This is the shape ``computed_default_summary_stats`` and ``histogram``
    expect. Counts are cast to int64 to match the previous ``.to_list()``
    path's effective dtype and keep ``categorical_dict``'s
    ``full_long_tail - unique_count`` subtraction signed (polars returns
    uint32, which underflows on 0-N).
    """
    counts = vc['count'].to_numpy().astype(np.int64, copy=False)
    return pd.Series(counts, index=vc[name].to_numpy())


def batch_value_counts(df: pl.DataFrame, columns: Optional[Iterable[str]] = None) -> Dict[str, pd.Series]:
    """value_counts for every column in one ``pl.collect_all``, as
    ``{column: pd.Series}`` in the shape ``vc_frame_to_pd`` produces.

    One lazy select per column lets polars run the group-bys across columns
    in parallel instead of one Series at a time (#997). Object columns are
    left out: ``collect_all`` panics on them rather than raising, so they
    stay on the per-Series path.
    """
    if columns is None:
        columns = df.columns
    names = [c for c in columns if df.schema[c] != pl.Object]
    lazy = df.lazy()
    frames = pl.collect_all([
        lazy.select(pl.col(c).drop_nulls().value_counts(sort=True)).unnest(c) for c in names])
    return {c: vc_frame_to_pd(vc, c) for c, vc in zip(names, frames)}
