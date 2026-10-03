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
from io import BytesIO
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


# --- #995: paging must be repeatable across ties in the sort column ---------
#
# ``handle_infinite_request_buckaroo_polars`` sorts on the one requested
# column. Polars leaves the order of equal keys unspecified when
# ``maintain_order`` is False (the default), so a host can't promise that
# the same window request returns the same rows. The handler adds the
# row index (``with_row_index()``, file order) as a trailing ascending
# sort key so ties are broken deterministically. These tests pin that.
#
# The polars build on hand happens to keep ties in input order for a
# single-key sort, so the behavioural tests would pass by accident
# against the old code. ``unstable_sort`` perturbs each sort call the
# way polars is allowed to -- it shuffles the rows (with a different
# seed per call) before handing them to the real ``sort`` -- so ties come
# out in a different order on every call unless the handler names a
# tie-break key.

def _tie_frame(n=600, groups=6):
    """``g`` has ``groups`` distinct values, each repeated ``n/groups``
    times in a round-robin, so every window of a sort on ``g`` is all
    ties. ``v`` is unique and in file order."""
    return pl.DataFrame({"g": [i % groups for i in range(n)], "v": list(range(n))})


def _sorted_window(dataflow, sort_direction, start=0, end=50):
    payload = {"start": start, "end": end, "sort": "a", "sort_direction": sort_direction}
    msg, parquet_bytes = handle_infinite_request_buckaroo_polars(dataflow, payload)
    assert "error_info" not in msg, msg.get("error_info")
    return pl.read_parquet(BytesIO(parquet_bytes))


@pytest.fixture
def unstable_sort(monkeypatch):
    """Make ``pl.DataFrame.sort`` order ties differently on every call.

    Shuffles the frame with a fresh seed, then runs the real sort with
    ``maintain_order=True`` so the shuffled order is exactly what ties
    come out in. A sort whose keys fully determine the row order is
    unaffected; a sort that leaves ties to polars sees them permuted."""
    real_sort = pl.DataFrame.sort
    calls = {"n": 0}

    def shuffled_sort(self, *args, **kwargs):
        calls["n"] += 1
        shuffled = self.sample(fraction=1.0, shuffle=True, seed=calls["n"])
        kwargs["maintain_order"] = True
        return real_sort(shuffled, *args, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "sort", shuffled_sort)
    return calls


def test_sorted_window_is_identical_across_repeated_requests(unstable_sort):
    """The same ``sort``/``start``/``end`` request must return the same
    rows every time, even when the window is entirely ties."""
    dataflow = create_polars_dataflow(_tie_frame())
    windows = [_sorted_window(dataflow, "asc")["index"].to_list() for _ in range(5)]
    assert unstable_sort["n"] == 5
    assert all(w == windows[0] for w in windows), (
        f"window differed across calls: {[w[:5] for w in windows]}")


def test_sort_asc_breaks_ties_by_ascending_row_index(unstable_sort):
    """Within a run of equal ``g`` values the rows appear in file order
    (ascending ``index``)."""
    dataflow = create_polars_dataflow(_tie_frame())
    window = _sorted_window(dataflow, "asc")
    assert window["a"].to_list() == [0] * 50
    idx = window["index"].to_list()
    assert idx == sorted(idx), f"ties not in ascending index order: {idx[:10]}"
    assert idx == list(range(0, 300, 6))


def test_sort_desc_breaks_ties_by_ascending_row_index(unstable_sort):
    """A descending sort reverses the sort column only -- ties still come
    out in ascending ``index`` (file order), not reversed."""
    dataflow = create_polars_dataflow(_tie_frame())
    window = _sorted_window(dataflow, "desc")
    assert window["a"].to_list() == [5] * 50
    idx = window["index"].to_list()
    assert idx == sorted(idx), f"ties not in ascending index order: {idx[:10]}"
    assert idx == list(range(5, 305, 6))


@pytest.mark.parametrize("direction, expected_descending", [("asc", [False, False]), ("desc", [True, False])])
def test_sort_key_list_includes_row_index(monkeypatch, direction, expected_descending):
    """Direct check on the sort call: keys are ``[sort_col, "index"]`` and
    the index is always ascending, whatever the direction of the sort
    column."""
    real_sort = pl.DataFrame.sort
    captured = []

    def capturing_sort(self, by, *more_by, **kwargs):
        captured.append((by, kwargs.get("descending")))
        return real_sort(self, by, *more_by, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "sort", capturing_sort)
    dataflow = create_polars_dataflow(_tie_frame())
    _sorted_window(dataflow, direction)
    assert len(captured) == 1, captured
    by, descending = captured[0]
    assert list(by) == ["g", "index"], f"sort keys {by!r} should end with the row index"
    assert list(descending) == expected_descending, (
        f"index key must always be ascending, got descending={descending!r}")
