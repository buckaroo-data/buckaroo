#!/usr/bin/env python3
"""Smoke tests for verifying buckaroo installs correctly with various extras.

Usage:
    python scripts/smoke_test.py base
    python scripts/smoke_test.py polars
    python scripts/smoke_test.py mcp
    python scripts/smoke_test.py marimo
    python scripts/smoke_test.py jupyterlab
    python scripts/smoke_test.py notebook
"""
import sys


def test_base():
    """Bare `pip install buckaroo` — no pandas required (pandas is optional)."""
    import buckaroo  # noqa: F401
    from buckaroo._version import __version__
    assert __version__, "version should be set"

    # Verify pyarrow is available (core dep)
    import pyarrow  # noqa: F401

    # If pandas is available, test the full dataflow pipeline
    try:
        import pandas as pd
        from buckaroo.dataflow.dataflow import CustomizableDataflow
        from buckaroo.dataflow.autocleaning import PandasAutocleaning
        from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf
        from buckaroo.serialization_utils import pd_to_obj, to_parquet

        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

        class TestDataflow(CustomizableDataflow):
            autocleaning_klass = PandasAutocleaning
            autoclean_conf = tuple([NoCleaningConf])

        flow = TestDataflow(df)
        assert flow.processed_df is not None, "processed_df should not be None"
        assert len(flow.processed_df) == 3

        parquet_bytes = to_parquet(df)
        assert len(parquet_bytes) > 0, "parquet serialization should produce bytes"

        obj = pd_to_obj(df)
        assert len(obj) > 0, "pd_to_obj should produce non-empty output"
    except ImportError:
        pass  # pandas not installed — that's OK for base install

    print("  base: OK")


def test_polars():
    """pip install buckaroo[polars]"""
    import polars as pl
    from buckaroo.polars_buckaroo import PolarsBuckarooWidget, to_parquet

    df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

    # Verify polars parquet serialization
    parquet_bytes = to_parquet(df.with_row_index())
    assert len(parquet_bytes) > 0, "polars parquet serialization should produce bytes"

    # Verify polars widget class is importable
    assert PolarsBuckarooWidget is not None

    print("  polars: OK")


def test_mcp():
    """pip install buckaroo[mcp]"""
    import mcp  # noqa: F401
    import tornado  # noqa: F401

    # Verify MCP tool module is importable
    import buckaroo_mcp_tool  # noqa: F401
    assert hasattr(buckaroo_mcp_tool, "main")

    # Verify server module imports work (uses tornado)
    from buckaroo.server.app import make_app  # noqa: F401

    print("  mcp: OK")


def test_marimo():
    """pip install buckaroo[marimo]"""
    import marimo  # noqa: F401
    from buckaroo.marimo_utils import (  # noqa: F401
        marimo_monkeypatch,
        marimo_unmonkeypatch,
        BuckarooDataFrame,
    )

    print("  marimo: OK")


def test_jupyterlab():
    """pip install buckaroo[jupyterlab]"""
    import jupyterlab
    major = int(jupyterlab.__version__.split(".")[0])
    assert major >= 3, f"jupyterlab {jupyterlab.__version__} too old"

    print("  jupyterlab: OK")


def test_notebook():
    """pip install buckaroo[notebook]"""
    import notebook
    major = int(notebook.__version__.split(".")[0])
    assert major >= 7, f"notebook {notebook.__version__} too old"

    print("  notebook: OK")


TESTS = {
    "base": test_base,
    "polars": test_polars,
    "mcp": test_mcp,
    "marimo": test_marimo,
    "jupyterlab": test_jupyterlab,
    "notebook": test_notebook,
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <{'|'.join(TESTS.keys())}>")
        sys.exit(1)

    name = sys.argv[1]
    if name not in TESTS:
        print(f"Unknown test: {name!r}. Choose from: {', '.join(TESTS.keys())}")
        sys.exit(1)

    try:
        TESTS[name]()
    except Exception as e:
        print(f"  {name}: FAILED — {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
