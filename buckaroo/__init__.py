# -*- coding: utf-8 -*-
from ._version import __version__
from .buckaroo_widget import BuckarooWidget
from .dataflow.widget_extension_utils import DFViewer
from .widget_utils import is_in_ipython, enable, disable, determine_jupter_env


def _jupyter_nbextension_paths():
    """Called by Jupyter Notebook Server to detect if it is a valid nbextension and
    to install the widget
    Returns
    =======
    section: The section of the Jupyter Notebook Server to change.
        Must be 'notebook' for widget extensions
    src: Source directory name to copy files from. Webpack outputs generated files
        into this directory and Jupyter Notebook copies from this directory during
        widget installation
    dest: Destination directory name to install widget files to. Jupyter Notebook copies
        from `src` directory into <jupyter path>/nbextensions/<dest> directory
        during widget installation
    require: Path to importable AMD Javascript module inside the
        <jupyter path>/nbextensions/<dest> directory
    """
    return [{
        'section': 'notebook',
        'src': 'nbextension',
        'dest': "buckaroo",
        'require': 'buckaroo/extension'
    }]


def _jupyter_labextension_paths():
    """Called by Jupyter Lab Server to detect if it is a valid labextension and
    to install the widget
    Returns
    =======
    src: Source directory name to copy files from. Webpack outputs generated files
        into this directory and Jupyter Lab copies from this directory during
        widget installation
    dest: Destination directory name to install widget files to. Jupyter Lab copies
        from `src` directory into <jupyter path>/labextensions/<dest> directory
        during widget installation
    """
    return [{
        'src': 'labextension',
        'dest': "buckaroo"
    }]




def is_notebook_compatible():
    jupyter_env = determine_jupter_env()
    if jupyter_env == "jupyter-notebook":
        try:
            import notebook
            return notebook.version_info[0] >= 7
        except:
            pass
        return False
    else:
        return True

def warn_on_incompatible():
    if not is_notebook_compatible():
        import notebook
        print("Buckaroo is compatible with jupyter notebook > 7, or jupyterlab >3.6.0")
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
    if is_in_ipython():
        enable()
        print("Buckaroo has been enabled as the default DataFrame viewer.  To return to default dataframe visualization use `from buckaroo import disable; disable()`")
    else:
        print("must be running inside ipython to enable default display via enable()")


    warn_on_incompatible()
except:
    print("error enabling buckaroo as default display formatter for dataframes (ignore message during testing/builds")


