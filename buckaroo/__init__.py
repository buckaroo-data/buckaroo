# -*- coding: utf-8 -*-
from ._version import __version__
from .buckaroo_widget import BuckarooWidget, enable, disable


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


def debug_packages():
    print("Selected Jupyter core packages...")
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
    enable()
except:
    print("error enabling buckaroo as default display formatter for dataframes (ignore message during testing/builds")


