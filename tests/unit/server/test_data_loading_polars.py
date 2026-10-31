"""Unit tests for ``buckaroo.server.data_loading_polars``.

Covers behaviour added in PR #855 (``backend='polars'`` for ``/load``)
and pins parity with the pandas path on two edge cases flagged in code
review:

* Search across a frame with no string columns returns 0 rows (matches
  ``search_df_str`` semantics so the UI doesn't appear unfiltered).
* ``.json`` files are read as standard JSON arrays (matches
  ``pd.read_json`` default ``lines=False`` so the same file loads under
  either backend).
"""
import json
import os
import tempfile

import polars as pl
import pytest

from buckaroo.server.data_loading_polars import (create_polars_dataflow, handle_infinite_request_buckaroo_polars, load_file_polars)


def _payload(start=0, end=100):
    return {"start": start, "end": end}


def test_search_with_no_string_columns_returns_empty():
    """P1 (#855 codex): non-empty search on a numeric-only frame must
    return 0 rows. The pandas path's ``search_df_str`` OR-accumulates
    matches over string/object columns starting from an all-False mask,
    so a frame with no such columns produces an empty result. The polars
    handler must match — otherwise users see the full frame and assume
    search is broken."""
    df = pl.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
    dataflow = create_polars_dataflow(df)
    msg, _parquet = handle_infinite_request_buckaroo_polars(
        dataflow, _payload(), search_string="anything")
    assert msg["length"] == 0, (
        f"search on numeric-only frame should return 0 rows "
        f"(matching pandas search_df_str), got length={msg['length']}")


def test_search_with_string_columns_still_works():
    """Sanity check the fix doesn't break the happy path: a literal
    substring match on a frame with string columns should still filter
    to matching rows."""
    df = pl.DataFrame({"name": ["alice", "bob", "carol"], "x": [1, 2, 3]})
    dataflow = create_polars_dataflow(df)
    msg, _parquet = handle_infinite_request_buckaroo_polars(
        dataflow, _payload(), search_string="ali")
    assert msg["length"] == 1, f"expected 1 row matching 'ali', got {msg['length']}"


def test_load_file_polars_json_array():
    """P2 (#855 codex): ``.json`` must read a standard JSON array of
    records — matching ``pd.read_json`` default ``lines=False``. The
    initial implementation used ``pl.read_ndjson`` which only accepts
    newline-delimited JSON, so a file that loads fine under
    ``backend='pandas'`` would 500 under ``backend='polars'``."""
    records = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}, {"a": 3, "b": "z"}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(records, f)
        path = f.name
    try:
        df = load_file_polars(path)
        assert df.shape == (3, 2), f"expected (3, 2), got {df.shape}"
        assert sorted(df.columns) == ["a", "b"]
    finally:
        os.unlink(path)


def test_load_file_polars_ndjson_still_works():
    """Newline-delimited JSON should still load — via the ``.ndjson``
    extension. Keeps support for the format the original implementation
    handled, just behind a distinct extension so ``.json`` can mean
    standard JSON (matching pandas)."""
    records = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    with tempfile.NamedTemporaryFile("w", suffix=".ndjson", delete=False) as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        path = f.name
    try:
        df = load_file_polars(path)
        assert df.shape == (2, 2)
    finally:
        os.unlink(path)


def test_load_file_polars_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported file format"):
        load_file_polars("/tmp/foo.xyz")


def test_polars_server_dataflow_uses_polars_autocleaning():
    """#900: ``PolarsServerDataflow`` must use the polars-aware
    ``PolarsAutocleaning`` (like ``PolarsBuckarooWidget``), not
    ``PandasAutocleaning``."""
    from buckaroo.polars_buckaroo import PolarsAutocleaning, PolarsBuckarooWidget
    from buckaroo.server.data_loading_polars import PolarsServerDataflow

    assert PolarsServerDataflow.autocleaning_klass is PolarsAutocleaning
    assert (PolarsServerDataflow.autocleaning_klass
            is PolarsBuckarooWidget.autocleaning_klass)
    dataflow = create_polars_dataflow(pl.DataFrame({"a": [1, 2, 3]}))
    assert isinstance(dataflow.ac_obj, PolarsAutocleaning)


def test_polars_server_dataflow_autocleaning_with_add_orig():
    """With a real cleaning conf the polars ``make_origs`` path must run:
    the cleaned frame keeps the original column next to the cleaned one."""
    from typing import Any, TypedDict

    from buckaroo.customizations.pl_autocleaning_conf import NoCleaningConfPl
    from buckaroo.customizations.pl_stats_v2 import pl_cleaning_stats
    from buckaroo.customizations.polars_commands import (
        DropCol, FillNA, GroupBy, NoOp, PlSafeInt)
    from buckaroo.dataflow.autocleaning import AutocleaningConfig
    from buckaroo.pluggable_analysis_framework.stat_func import stat
    from buckaroo.server.data_loading_polars import PolarsServerDataflow

    _Result = TypedDict('_Result', {'cleaning_ops': Any, 'add_orig': Any})

    @stat()
    def _add_orig_cleaning(int_parse: float, int_parse_fail: float) -> _Result:
        if int_parse > 0.3:
            return {'cleaning_ops': [{'symbol': 'safe_int', 'meta': {'auto_clean': True}},
                                     {'symbol': 'df'}],
                    'add_orig': True}
        return {'cleaning_ops': [], 'add_orig': False}

    class IntCleaningConf(AutocleaningConfig):
        autocleaning_analysis_klasses = [pl_cleaning_stats, _add_orig_cleaning]
        command_klasses = [PlSafeInt, DropCol, FillNA, GroupBy, NoOp]
        name = "default"

    class CleaningServerDataflow(PolarsServerDataflow):
        autoclean_conf = tuple([IntCleaningConf, NoCleaningConfPl])

    df = pl.DataFrame({"realname": ["30", "40"]})
    dataflow = CleaningServerDataflow(df, skip_main_serial=True)
    dataflow.cleaning_method = "default"
    assert isinstance(dataflow.cleaned_df, pl.DataFrame)
    assert dataflow.cleaned_df.to_dicts() == [
        {"realname": 30, "realname_orig": "30"},
        {"realname": 40, "realname_orig": "40"}]
