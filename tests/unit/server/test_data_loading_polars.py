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
from io import BytesIO

import polars as pl
import pytest

from buckaroo.customizations.pl_lazy_stats import collect_lazy_stats
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


# ------------------------------------------------------------------
# Lazy sessions (#993): a /load with backend='polars' holds a LazyFrame
# over the file, not an eager frame, so no session keeps the whole
# table in memory. The dataflow and the infinite handler must work over
# that LazyFrame, collecting only the requested window.
# ------------------------------------------------------------------

N_ROWS = 1500


def _write_parquet(tmp_path):
    """1500-row frame: ``id`` 0..1499, ``name`` 'name<i>' with every
    100th row 'alice', ``val`` id * 0.5. Columns rewrite to a, b, c."""
    path = str(tmp_path / "lazy.parquet")
    pl.DataFrame({"id": list(range(N_ROWS)), "name": ["alice" if i % 100 == 0 else f"name{i}" for i in range(N_ROWS)],
        "val": [i * 0.5 for i in range(N_ROWS)]}).write_parquet(path)
    return path


def _window(dataflow, start, end, **extra):
    msg, parquet = handle_infinite_request_buckaroo_polars(
        dataflow, {"start": start, "end": end, **extra.pop("payload", {})}, **extra)
    assert "error_info" not in msg, msg.get("error_info")
    return msg, pl.read_parquet(BytesIO(parquet))


def test_lazy_dataflow_holds_lazyframe_not_dataframe(tmp_path):
    """The dataflow built from ``pl.scan_parquet`` must keep every frame
    slot lazy — raw, sampled, cleaned and processed. An eager
    ``pl.DataFrame`` anywhere on it means the whole file was read."""
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    for name in ("orig_df", "raw_df", "sampled_df", "cleaned_df", "processed_df"):
        frame = getattr(dataflow, name)
        assert isinstance(frame, pl.LazyFrame), f"{name} is {type(frame).__name__}, expected LazyFrame"
    _unused, processed_df, _sd = dataflow.widget_args_tuple
    assert isinstance(processed_df, pl.LazyFrame)


def test_lazy_df_meta_total_rows(tmp_path):
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    assert dataflow.df_meta["total_rows"] == N_ROWS
    assert dataflow.df_meta["filtered_rows"] == N_ROWS
    assert dataflow.df_meta["columns"] == 3


def test_lazy_window_first_page(tmp_path):
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    msg, df = _window(dataflow, 0, 100)
    assert msg["length"] == N_ROWS
    assert df["index"].to_list() == list(range(0, 100))
    assert df["a"].to_list() == list(range(0, 100))
    assert df["b"][0] == "alice" and df["b"][1] == "name1"


def test_lazy_window_second_page(tmp_path):
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    msg, df = _window(dataflow, 1000, 1100)
    assert msg["length"] == N_ROWS
    assert df["index"].to_list() == list(range(1000, 1100))
    assert df["a"].to_list() == list(range(1000, 1100))
    assert df["c"].to_list() == [i * 0.5 for i in range(1000, 1100)]


def test_lazy_sort_returns_right_order(tmp_path):
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    _msg, desc = _window(dataflow, 0, 5, payload={"sort": "a", "sort_direction": "desc"})
    assert desc["a"].to_list() == [1499, 1498, 1497, 1496, 1495]
    # row index carries the original position, as the eager path does
    assert desc["index"].to_list() == [1499, 1498, 1497, 1496, 1495]
    _msg, asc = _window(dataflow, 0, 5, payload={"sort": "a", "sort_direction": "asc"})
    assert asc["a"].to_list() == [0, 1, 2, 3, 4]


def test_lazy_search_filters_rows(tmp_path):
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    msg, df = _window(dataflow, 0, 100, search_string="alice")
    assert msg["length"] == N_ROWS // 100
    assert df["b"].to_list() == ["alice"] * (N_ROWS // 100)
    assert df["a"].to_list() == list(range(0, N_ROWS, 100))
    # the window index counts positions within the filtered result
    assert df["index"].to_list() == list(range(N_ROWS // 100))


def test_lazy_summary_stats_numeric_column(tmp_path):
    """Stats run as one lazy select over the scan. The numeric column's
    basics must be exact over the whole file, and the keys the lazy
    session can't produce are listed in df_meta so a client can tell."""
    dataflow = create_polars_dataflow(pl.scan_parquet(_write_parquet(tmp_path)))
    a = dataflow.merged_sd["a"]
    assert a["orig_col_name"] == "id"
    assert a["length"] == N_ROWS
    assert a["null_count"] == 0
    assert a["min"] == 0
    assert a["max"] == N_ROWS - 1
    assert a["_type"] == "integer"
    assert dataflow.merged_sd["b"]["_type"] == "string"
    assert "value_counts" in dataflow.df_meta["stats_omitted"]


def test_lazy_stats_over_a_sample_past_the_cap(tmp_path):
    """Exact distinct counts, value counts and quantiles aren't
    bounded-memory, so a scan over the cap is summarised from a sample of
    about ``sample_rows`` rows: the whole table is never the input."""
    stats = collect_lazy_stats(pl.scan_parquet(_write_parquet(tmp_path)), sample_rows=300)
    ident = stats["id"]
    assert 0 < ident["length"] <= 300
    assert ident["distinct_count"] <= ident["length"]
    assert ident["min"] == 0 and ident["max"] == N_ROWS - 1  # first and last rows are in the sample


def test_lazy_stats_under_the_cap_are_exact(tmp_path):
    stats = collect_lazy_stats(pl.scan_parquet(_write_parquet(tmp_path)), sample_rows=N_ROWS)
    assert stats["id"]["length"] == N_ROWS
    assert stats["id"]["distinct_count"] == N_ROWS
    assert stats["name"]["distinct_count"] == N_ROWS - N_ROWS // 100 + 1


def test_lazy_sort_with_search_matches_eager(tmp_path):
    """Sort and search together, with nulls in the sort column: the lazy
    window must equal the eager one, row index included."""
    path = str(tmp_path / "nulls.parquet")
    vals = [None if i % 7 == 0 else (i * 37) % 1000 + i / 10000 for i in range(N_ROWS)]
    pl.DataFrame({"v": vals, "s": ["alice" if i % 3 == 0 else f"n{i}" for i in range(N_ROWS)]}).write_parquet(path)
    lazy, eager = create_polars_dataflow(pl.scan_parquet(path)), create_polars_dataflow(pl.read_parquet(path))
    for direction in ("asc", "desc"):
        payload = {"sort": "a", "sort_direction": direction}
        _m, lazy_df = _window(lazy, 20, 60, payload=payload, search_string="alice")
        _m, eager_df = _window(eager, 20, 60, payload=payload, search_string="alice")
        assert lazy_df.equals(eager_df), direction
