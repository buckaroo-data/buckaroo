import pandas as pd
import buckaroo


#meant to be added to pd.DataFrame class 
def marimo_display_func(self):
    return buckaroo.BuckarooInfiniteWidget(self)




class BuckarooDataFrame(pd.DataFrame):
    """used for marimo, when you don't want to call
    marimo_monkeypatch so you can preserve regular pd.DataFrame
    display"""
    _display_ = marimo_display_func


def marimo_pl_display_func(self):
    from buckaroo.polars_buckaroo import PolarsBuckarooInfiniteWidget
    return PolarsBuckarooInfiniteWidget(self)

def get_polars_buckaroo_dataframe():
    #in a function so we don't bare import polars and cause an error
    import polars as pl


    class BuckarooPLDataFrame(pl.DataFrame):
        """used for marimo, when you don't want to call
        marimo_monkeypatch so you can preserve regular pd.DataFrame
        display"""
        _display_ = marimo_pl_display_func
    

    
def marimo_monkeypatch():
    pd.DataFrame._display_ = marimo_display_func
    try:
        import polars as pl
        pl.DataFrame._display_ = marimo_pl_display_func
    except ImportError:
        pass
        

def marimo_unmonkeypatch():
    if hasattr(pd.DataFrame, '_display_'):
        delattr(pd.DataFrame, '_display_')
    else:
        print("pd.DataFrame wasn't monkeypatched, doing nothing")
    try:
        import polars as pl
        if hasattr(pl.DataFrame, '_display_'):
            delattr(pl.DataFrame, '_display_')
        else:
            print("pl.DataFrame wasn't monkeypatched, doing nothing")
    except ImportError:
        pass

