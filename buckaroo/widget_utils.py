import traceback
from .buckaroo_widget import BuckarooWidget
import pandas as pd

def is_in_ipython():

    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        raise ImportError('This feature requires IPython 1.0+')
    
    ip = get_ipython()
    if ip is None:
        #print("must be running inside ipython to enable default display via enable()")
        return False
    return ip
    

def enable(sampled=True,
           summaryStats=False,
           reorderdColumns=False,
           showCommands=False,
           auto_clean=False,
           postProcessingF=None,
           debug=False
           ):
    """
    Automatically use buckaroo to display all DataFrames
    instances in the notebook.

    """

    ip = is_in_ipython()
    
    def _display_as_buckaroo(df):
        from IPython.display import display
        try:
            bw = BuckarooWidget(df,
                                debug=debug)
            return display(bw)
        except:
            if debug:
                traceback.print_exc()
                return
            # returning NotImplementedError causes IPython to find the
            # next registered formatter for the type
            raise NotImplementedError

    def _display_polars_as_buckaroo(polars_df):
        from IPython.display import display
        from buckaroo.polars_buckaroo import PolarsBuckarooWidget

        try:
            return display(PolarsBuckarooWidget(polars_df))
        except:
            if debug:
                traceback.print_exc()
                return
            raise NotImplementedError

    ip_formatter = ip.display_formatter.ipython_display_formatter
    ip_formatter.for_type(pd.DataFrame, _display_as_buckaroo)
    
    try:
        import polars as pl
        ip_formatter.for_type(pl.DataFrame, _display_polars_as_buckaroo)
    except ImportError:
        pass
    return True

def disable():
    """
    disable bucakroo as the default display method for DataFrames

    """

    ip = is_in_ipython()
    
    ip_formatter = ip.display_formatter.ipython_display_formatter
    ip_formatter.type_printers.pop(pd.DataFrame, None)
    
    try:
        import polars as pl
        ip_formatter.type_printers.pop(pl.DataFrame, None)    
    except ImportError:
        pass
    print("The default DataFrame displayers have been restored. To re-enable Buckaroo use `from buckaroo import enable; enable()`")
