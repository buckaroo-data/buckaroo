import pandas as pd
import numpy as np


def get_outlier_idxs(ser):
    if not pd.api.types.is_numeric_dtype(ser.dtype):
        return []
    outlier_idxs = []
    outlier_idxs.extend(ser.nlargest(5).index)
    outlier_idxs.extend(ser.nsmallest(5).index)
    return outlier_idxs


def polars_sample(df, sample_size=500, include_outliers=False):
    return df.sample(min(len(df), sample_size))

def sample(df, sample_size=500, include_outliers=False):
    include_outliers = False
    if len(df) <= sample_size:
        return df

    try:
        import polars
        if isinstance(df, polars.DataFrame):
            return polars_sample(df, sample_size, include_outliers)
    except ImportError:
        pass
    sdf = df.sample(np.min([sample_size, len(df)]))
    if True:
        return sdf
    #non_unique indexes are very slow
    if include_outliers and sdf.index.is_unique:
        outlier_idxs = []
        for col in df.columns:
            outlier_idxs.extend(get_outlier_idxs(df[col]) )
        outlier_idxs.extend(sdf.index)
        uniq_idx = np.unique(outlier_idxs)
        return df.loc[uniq_idx]
    return sdf

