# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

import pkg_resources
import json
import pathlib
full_path = pathlib.Path(__file__).parent.resolve()
try:
    __version__ = pkg_resources.get_distribution('buckaroo').version
except Exception:
    __version__ = json.loads(open(full_path / "../package.json").read())['version']
