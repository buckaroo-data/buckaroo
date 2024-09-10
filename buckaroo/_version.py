# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

from importlib import metadata
import json
import pathlib
full_path = pathlib.Path(__file__).parent.resolve()
try:
    __version__ = metadata.version('buckaroo')
except Exception:
    __version__ = json.loads(open(full_path / "../package.json").read())['version']
