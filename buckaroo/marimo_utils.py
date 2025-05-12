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


    
def marimo_monkeypatch():
    pd.DataFrame._display_ = marimo_display_func

def marimo_unmonkeypatch():
    if hasattr(pd.DataFrame, '_display_'):
        delattr(pd.DataFrame, '_display_')
    else:
        print("pd.DataFrame wasn't monkeypatched, doing nothing")

