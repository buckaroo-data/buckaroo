from .buckaroo_widget import BuckarooWidget
import pandas as pd

def _display_as_buckaroo(df):
    from IPython.display import display
    return display(BuckarooWidget(df, showCommands=False))


def _display_polars_as_buckaroo(polars_df):
    from IPython.display import display
    pandas_df = polars_df.to_pandas()
    return display(BuckarooWidget(pandas_df, showCommands=False))


def enable():
    """
    Automatically use buckaroo to display all DataFrames
    instances in the notebook.

    """
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        raise ImportError('This feature requires IPython 1.0+')

    ip = get_ipython()
    if ip is None:
        print("must be running inside ipython to enable default display via enable()")
        return
    ip_formatter = ip.display_formatter.ipython_display_formatter
    ip_formatter.for_type(pd.DataFrame, _display_as_buckaroo)
    

    try:
        import polars as pl
        ip_formatter.for_type(pl.DataFrame, _display_polars_as_buckaroo)
    except ImportError:
        pass

def disable():
    """
    disable bucakroo as the default display method for DataFrames

    """
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        raise ImportError('This feature requires IPython 1.0+')

    ip = get_ipython()
    
    ip_formatter = ip.display_formatter.ipython_display_formatter
    ip_formatter.type_printers.pop(pd.DataFrame, None)    
    try:
        import polars as pl
        ip_formatter.type_printers.pop(pl.DataFrame, None)    
    except ImportError:
        pass

