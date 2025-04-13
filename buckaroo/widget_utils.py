import traceback
from .buckaroo_widget import BuckarooInfiniteWidget
import pandas as pd
from datetime import datetime as dtdt
import os


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

def is_in_marimo():
    try:
        import marimo
    except ImportError:
        return False
    return marimo.running_in_notebook()
    

def enable(buckaroo_kls=BuckarooInfiniteWidget,
           debug=False,
           ):
    """
    Automatically use buckaroo to display all DataFrames
    instances in the notebook.

    """

    ip = is_in_ipython()
    try:
        import psutil
        parent_process = psutil.Process().parent()
        server_start_time = dtdt.fromtimestamp(parent_process.create_time())

        buckaroo_mtime = dtdt.fromtimestamp(os.path.getmtime(__file__))
        buckaroo_installed_after_server_start = buckaroo_mtime > server_start_time
    except ImportError:
        buckaroo_installed_after_server_start = False

    jupyter_env = determine_jupter_env()
    if jupyter_env in ["jupyter-lab", "jupyter-notebook"] and buckaroo_installed_after_server_start:
        print("It looks like you installed Buckaroo after you started this notebook server.")
        print("""If you see a messages like""")
        print(""""Failed to load model class 'DCEFWidgetModel' from module 'buckaroo'" """)
        print("""restart the jupyter server and try again.""")
        print("""If you have furter errors, please file a bug report at https://github.com/paddymul/buckaroo""")
        print("-"*80)
        print("buckaroo_mtime", buckaroo_mtime, "server_start_time", server_start_time)
        #note we don't throw an exception here because this is a
        #warning. I think this usecase specifically works on google
        #colab


    
    def _display_as_buckaroo(df):
        from IPython.display import display
        try:
            bw = buckaroo_kls(df, debug=debug)
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

    def _display_geopandas_as_buckaroo(gdf):
        from IPython.display import display
        from buckaroo.geopandas_buckaroo import GeopandasBuckarooWidget

        try:
            return display(GeopandasBuckarooWidget(gdf))
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

    try:
        import geopandas
        ip_formatter.for_type(geopandas.geodataframe.GeoDataFrame, _display_geopandas_as_buckaroo)
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

def determine_jupter_env():
    jupyterlite = False
    try:
        import psutil
    except ImportError:
        jupyterlite = True

    if is_in_marimo():
        if jupyterlite:
            return "marimo-jupyterlite"
        else:
            return "marimo"
    if jupyterlite:
        return "jupyterlite"

    parent_process = psutil.Process().parent().cmdline()[-1]

    if 'jupyter-lab' in parent_process:
        return "jupyter-lab"
    elif 'jupyter-notebook' in parent_process:
        return "jupyter-notebook"
    elif '__vsc_ipynb_file__' in globals():
        return "vscode"
    else:
        try:
            from IPython.core import getipython
            if 'google.colab' in str(getipython.get_ipython()):
                return "google-colab"
        except:
            pass
    return "unknown"

