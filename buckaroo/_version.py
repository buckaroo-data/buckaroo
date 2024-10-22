# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

from importlib import metadata
import json
import pathlib
full_path = pathlib.Path(__file__).parent.resolve()
__version__ = "unknown"
try:
    __version__ = metadata.version('buckaroo')
except Exception:
    try:
        __version__ = json.loads(open(full_path / "../package.json").read())['version']
    except Exception:
        #Jupyter lite can't read this file for some reason
        __version__ = "0.7.8"
