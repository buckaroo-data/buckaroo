# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

import pkg_resources

try:
    __version__ = pkg_resources.get_distribution('buckaroo').version
except Exception:
    import json
    __version__ = json.loads(open("../package.json").read())['version']
