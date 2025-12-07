# -*- coding: utf-8 -*-
from ._version import __version__
from .buckaroo_widget import BuckarooWidget, BuckarooInfiniteWidget, AutocleaningBuckaroo
from .dataflow.widget_extension_utils import DFViewer
from .widget_utils import is_in_ipython, is_in_marimo, enable, disable, determine_jupter_env
from .read_utils import read
from .file_cache.cache_utils import (
    get_global_file_cache,
    get_global_executor_log,
    ensure_executor_sqlite,
    get_cache_size,
    clear_file_cache,
    clear_executor_log,
    clear_oldest_cache_entries,
    format_cache_size,
)



def is_notebook_compatible():
    jupyter_env = determine_jupter_env()
    if jupyter_env == "jupyter-notebook":
        try:
            import notebook
            return notebook.version_info[0] >= 6
        except:
            pass
        return False
    else:
        return True

def warn_on_incompatible():
    if not is_notebook_compatible():
        import notebook
        print("Buckaroo is compatible with jupyter notebook > 6, or jupyterlab >3.6.0")
        print("You seem to be executing this in jupyter notebook version %r" % str(notebook.__version__))
        print("You can upgrade to notebook 7 by running 'pip install --upgrade notebook'")
        print("Or you can try running jupyter lab with 'jupyter lab'")
        
              

def debug_packages():
    print("Selected Jupyter core packages...")
    jupyter_env = determine_jupter_env()
    print("executing in %s " % jupyter_env)
    packages = [
            "buckaroo",
            "jupyterlab",
            "notebook",
            "ipywidgets",
            "traitlets",
            "jupyter_core",
            "pandas",
            "numpy",
            "IPython",
            "ipykernel",
            "jupyter_client",
            "jupyter_server",
            "nbclient",
            "nbconvert",
            "nbformat",
            "qtconsole",
    ]
    
    for package in packages:
        try:
            mod = __import__(package)
            version = mod.__version__
        except ImportError:
            version = "not installed"
        print(f"{package:<17}:", version)
    for package in packages:
        try:
            mod = __import__(package)
            path = mod.__file__
        except ImportError:
            path = "not installed"
        print(f"{package:<17}:", path)

try:
    if is_in_marimo():
        print("Buckaroo has been enabled as the default DataFrame viewer.  To return to default dataframe visualization use `from buckaroo.marimo_utils import marimo_unmonkeypatch; marimo_unmonkeypatch()`")
        from buckaroo.marimo_utils import marimo_monkeypatch
        marimo_monkeypatch()

    elif is_in_ipython():
        enable()
        print("Buckaroo has been enabled as the default DataFrame viewer.  To return to default dataframe visualization use `from buckaroo import disable; disable()`")
    
    else:
        print("must be running inside ipython to enable default display via enable()")


    warn_on_incompatible()
except:
    print("error enabling buckaroo as default display formatter for dataframes (ignore message during testing/builds")


