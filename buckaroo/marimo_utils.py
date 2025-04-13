from functools import cache
import pandas as pd
import buckaroo

class BuckarooDataFrame(pd.DataFrame):
    """ used for marimo """
    def _display_(self):
        return buckaroo.BuckarooInfiniteWidget(self)

@cache
def marimo_monkeypatch():
    if pd.read_csv.__name__ == "read_csv":
        orig_read_csv = pd.read_csv
    else:
        raise Exception("it should only be possible to call marimo monkeypatch once")
    
    def bu_read_csv(*args, **kwargs):
        _df = orig_read_csv(*args, **kwargs)
        return BuckarooDataFrame(_df)
    
    if pd.read_parquet.__name__ == "read_parquet":
        orig_read_parquet = pd.read_parquet
    else:
        raise Exception("it should only be possible to call marimo monkeypatch once")

    def bu_read_parquet(*args, **kwargs):
        _df = orig_read_parquet(*args, **kwargs)
        return BuckarooDataFrame(_df)
    pd.read_csv = bu_read_csv
    pd.read_parquet = bu_read_parquet
