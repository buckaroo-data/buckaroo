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
import sys
import tempfile
from io import BytesIO

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from buckaroo.polars_buckaroo import prepare_df_for_serialization
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


# --- Row-order cache for the infinite handler (#993) -------------------
#
# Each window request used to re-filter and re-sort the whole frame.
# These tests count the frame-level calls that do that work, so a
# cached window must not add to the count. Both the frame-level sort
# (``DataFrame.sort``) and the series-level ``arg_sort`` are counted,
# so the assertion is "the sort column was sorted once", whichever API
# does it. Likewise ``DataFrame.filter`` and ``pl.arg_where`` for the
# search. Only calls made from ``buckaroo.*`` count, so the test-side
# reference computation doesn't add to the tally.


def _called_from_buckaroo():
    return sys._getframe(2).f_globals.get("__name__", "").startswith("buckaroo.")


def _sort_df():
    # Distinct sort keys with a null, so sorted output is unambiguous
    # and the null-placement default is covered.
    return pl.DataFrame({"name": ["alice", "bob", "carol", "dave", "alan", "fay"], "x": [3, None, 4, 1, 5, 2]})


def _decode(parquet_bytes):
    return pl.read_parquet(BytesIO(parquet_bytes))


def _reference_window(processed_df, search_string, start, end, sort_col=None, descending=False):
    """The pre-cache handler, inlined: filter, row-index, sort, slice."""
    if search_string:
        string_cols = [c for c, dt in zip(processed_df.columns, processed_df.dtypes) if dt == pl.String]
        mask = pl.any_horizontal(pl.col(c).str.contains(search_string, literal=True) for c in string_cols)
        filtered = processed_df.filter(mask)
    else:
        filtered = processed_df
    indexed = filtered.with_row_index()
    if sort_col:
        indexed = indexed.sort(sort_col, descending=descending)
    return prepare_df_for_serialization(indexed[start:end])


@pytest.fixture
def sort_counter(monkeypatch):
    calls = []
    orig_sort, orig_arg_sort = pl.DataFrame.sort, pl.Series.arg_sort

    def counting_sort(self, *args, **kwargs):
        if _called_from_buckaroo():
            calls.append("sort")
        return orig_sort(self, *args, **kwargs)

    def counting_arg_sort(self, *args, **kwargs):
        if _called_from_buckaroo():
            calls.append("arg_sort")
        return orig_arg_sort(self, *args, **kwargs)
    monkeypatch.setattr(pl.DataFrame, "sort", counting_sort)
    monkeypatch.setattr(pl.Series, "arg_sort", counting_arg_sort)
    return calls


@pytest.fixture
def filter_counter(monkeypatch):
    calls = []
    orig_filter, orig_arg_where = pl.DataFrame.filter, pl.arg_where

    def counting_filter(self, *args, **kwargs):
        if _called_from_buckaroo():
            calls.append("filter")
        return orig_filter(self, *args, **kwargs)

    def counting_arg_where(*args, **kwargs):
        if _called_from_buckaroo():
            calls.append("arg_where")
        return orig_arg_where(*args, **kwargs)
    monkeypatch.setattr(pl.DataFrame, "filter", counting_filter)
    monkeypatch.setattr(pl, "arg_where", counting_arg_where)
    return calls


def test_same_sort_two_windows_sorts_once(sort_counter):
    dataflow = create_polars_dataflow(_sort_df())
    processed_df = dataflow.widget_args_tuple[1]
    payload = {"sort": "b", "sort_direction": "asc"}
    for start, end in [(0, 3), (3, 6)]:
        msg, parquet = handle_infinite_request_buckaroo_polars(dataflow, {**payload, "start": start, "end": end})
        assert "error_info" not in msg, msg.get("error_info")
        assert msg["length"] == 6
        assert_frame_equal(_decode(parquet), _reference_window(processed_df, "", start, end, "x"))
    assert len(sort_counter) == 1, f"expected one sort for two windows of the same sort, got {sort_counter}"


def test_different_sort_sorts_again(sort_counter):
    dataflow = create_polars_dataflow(_sort_df())
    processed_df = dataflow.widget_args_tuple[1]
    handle_infinite_request_buckaroo_polars(dataflow, {"start": 0, "end": 3, "sort": "b", "sort_direction": "asc"})
    handle_infinite_request_buckaroo_polars(dataflow, {"start": 0, "end": 3, "sort": "b", "sort_direction": "asc"})
    assert len(sort_counter) == 1
    msg, parquet = handle_infinite_request_buckaroo_polars(
        dataflow, {"start": 0, "end": 3, "sort": "b", "sort_direction": "desc"})
    assert len(sort_counter) == 2, f"a direction change must sort again, got {sort_counter}"
    assert_frame_equal(_decode(parquet), _reference_window(processed_df, "", 0, 3, "x", descending=True))
    handle_infinite_request_buckaroo_polars(dataflow, {"start": 0, "end": 3, "sort": "a", "sort_direction": "asc"})
    assert len(sort_counter) == 3, f"a column change must sort again, got {sort_counter}"


def test_sort_with_search_matches_uncached_and_sorts_once(sort_counter):
    dataflow = create_polars_dataflow(_sort_df())
    processed_df = dataflow.widget_args_tuple[1]
    payload = {"sort": "b", "sort_direction": "desc"}
    for start, end in [(0, 2), (2, 4)]:
        msg, parquet = handle_infinite_request_buckaroo_polars(
            dataflow, {**payload, "start": start, "end": end}, search_string="a")
        assert "error_info" not in msg, msg.get("error_info")
        assert msg["length"] == 5  # alice, carol, dave, alan, fay
        assert_frame_equal(_decode(parquet), _reference_window(processed_df, "a", start, end, "x", descending=True))
    assert len(sort_counter) == 1, f"expected one sort for two windows of the same search+sort, got {sort_counter}"


def test_same_search_two_windows_filters_once(filter_counter):
    dataflow = create_polars_dataflow(_sort_df())
    processed_df = dataflow.widget_args_tuple[1]
    for start, end in [(0, 2), (2, 4)]:
        msg, parquet = handle_infinite_request_buckaroo_polars(
            dataflow, {"start": start, "end": end}, search_string="a")
        assert "error_info" not in msg, msg.get("error_info")
        assert_frame_equal(_decode(parquet), _reference_window(processed_df, "a", start, end))
    assert len(filter_counter) == 1, f"expected one filter for two windows of the same search, got {filter_counter}"


def test_quick_command_change_invalidates_row_order_cache(sort_counter):
    """A dataflow rerun replaces ``processed_df``; the cached order for
    the old frame must not be served against the new one."""
    dataflow = create_polars_dataflow(_sort_df())
    payload = {"start": 0, "end": 3, "sort": "b", "sort_direction": "asc"}
    msg, _ = handle_infinite_request_buckaroo_polars(dataflow, payload)
    assert msg["length"] == 6
    handle_infinite_request_buckaroo_polars(dataflow, payload)
    assert len(sort_counter) == 1
    dataflow.quick_command_args = {"search": ["a"]}
    processed_df = dataflow.widget_args_tuple[1]
    msg, parquet = handle_infinite_request_buckaroo_polars(dataflow, payload)
    assert "error_info" not in msg, msg.get("error_info")
    assert msg["length"] == len(processed_df) < 6
    assert len(sort_counter) == 2, f"a rerun must sort the new processed_df, got {sort_counter}"
    assert_frame_equal(_decode(parquet), _reference_window(processed_df, "", 0, 3, "x"))


def test_row_order_cache_is_bounded(sort_counter):
    """Four distinct sorts all stay cached; a fifth evicts the oldest
    (the cache keeps the last four), so the first sorts again."""
    dataflow = create_polars_dataflow(_sort_df())
    four_sorts = [("a", "asc"), ("a", "desc"), ("b", "asc"), ("b", "desc")]
    for col, direction in four_sorts + four_sorts:
        handle_infinite_request_buckaroo_polars(dataflow,
            {"start": 0, "end": 2, "sort": col, "sort_direction": direction})
    assert len(sort_counter) == 4, f"four distinct sorts requested twice should sort four times, got {sort_counter}"
    handle_infinite_request_buckaroo_polars(
        dataflow, {"start": 0, "end": 2, "sort": "a", "sort_direction": "asc"}, search_string="a")
    assert len(sort_counter) == 5
    handle_infinite_request_buckaroo_polars(dataflow, {"start": 0, "end": 2, "sort": "a", "sort_direction": "asc"})
    assert len(sort_counter) == 6, f"the oldest order should have been evicted, got {sort_counter}"
