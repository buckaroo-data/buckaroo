
import os
import subprocess
import sys

import pandas as pd
import pandera.pandas as pa
import pytest
from pandera import Column, Check
from buckaroo.contrib.buckaroo_pandera import BuckarooPandera


def test_buckaroo_pandera():
    fruits = pd.DataFrame({"name": ["apple", "banana", "apple", "orange"],
        "store": ["Aldi", "Walmart", "Walmart", "Aldi"], "price": [-3, 1, 2, 4]})
    available_fruits = ["apple", "banana", "orange"]
    nearby_stores = ["Aldi", "Walmart"]

    schema = pa.DataFrameSchema({"name": Column(str, Check.isin(available_fruits)),
        "store": Column(str, Check.isin(nearby_stores)), "price": Column(int, Check.greater_than(0))})
    BuckarooPandera(fruits, schema)
    assert 1==1


TZ_ENV = "PYARROW_IGNORE_TIMEZONE"


@pytest.mark.parametrize("before, after", [(None, "<unset>"), ("0", "0")])
def test_importing_buckaroo_pandera_leaves_pyarrow_ignore_timezone_alone(before, after):
    """pandera sets ``PYARROW_IGNORE_TIMEZONE=1`` on import, which makes pyarrow
    shift aware datetimes by their UTC offset. Importing buckaroo's pandera
    integration must not leave that in the process environment (#1058).

    Runs in a subprocess because pandera is already imported in this one.
    """
    env = {k: v for k, v in os.environ.items() if k != TZ_ENV}
    if before is not None:
        env[TZ_ENV] = before
    script = (
        "import os, buckaroo.contrib.buckaroo_pandera; "
        f"print(os.environ.get({TZ_ENV!r}, '<unset>'))"
    )
    out = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == after


def test_aware_datetime_survives_pyarrow_after_importing_buckaroo_pandera():
    env = {k: v for k, v in os.environ.items() if k != TZ_ENV}
    script = (
        "import datetime as dt, zoneinfo, pyarrow as pa\n"
        "import buckaroo.contrib.buckaroo_pandera\n"
        "v = dt.datetime(2020, 1, 1, tzinfo=zoneinfo.ZoneInfo('America/New_York'))\n"
        "typ = pa.timestamp('us', tz='America/New_York')\n"
        "assert pa.array([v], typ).to_pylist() == [v], pa.array([v], typ).to_pylist()\n"
    )
    subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True)


def test_the_test_session_does_not_run_under_pyarrow_ignore_timezone():
    """Collecting this file imports pandera, which sets the variable for every
    test in the session. ``tests/unit/conftest.py`` clears it (#1058)."""
    assert TZ_ENV not in os.environ
