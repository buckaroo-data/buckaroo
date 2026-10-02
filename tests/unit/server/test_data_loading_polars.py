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
import random
import tempfile
from io import BytesIO

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


# --- row_order_column tie-break (#995) -----------------------------------
#
# A host that writes a no-ties row-order column (tallyman's ``__row_order``)
# names it on ``/load``; the handler then orders every page by
# ``[sort_col, row_order_column]`` (or by ``row_order_column`` alone when
# there is no sort) so the same request always returns the same rows.
# The fixture shuffles ``ro`` relative to file order so an input-order
# tie-break (``maintain_order``) can't pass these by accident.

def _tie_frame(n=300, groups=5, seed=0):
    rng = random.Random(seed)
    ro = list(range(n))
    rng.shuffle(ro)
    return pl.DataFrame({"g": [rng.randrange(groups) for _ in range(n)], "ro": ro})


def _page(dataflow, start, end, sort=None, sort_direction="asc", **kw):
    payload = {"start": start, "end": end}
    if sort:
        payload["sort"] = sort
        payload["sort_direction"] = sort_direction
    msg, parquet = handle_infinite_request_buckaroo_polars(dataflow, payload, **kw)
    assert "error_info" not in msg, msg.get("error_info")
    # Columns come back renamed: a=g, b=ro, plus the row index.
    return pl.read_parquet(BytesIO(parquet))


def _ro_ascending_within_ties(page):
    rows = list(zip(page["a"].to_list(), page["b"].to_list()))
    for (g0, ro0), (g1, ro1) in zip(rows, rows[1:]):
        if g0 == g1 and ro1 < ro0:
            return False
    return True


def test_row_order_column_breaks_ties_ascending():
    dataflow = create_polars_dataflow(_tie_frame())
    pages = [_page(dataflow, 0, 50, sort="a", row_order_column="ro") for _ in range(5)]
    for p in pages[1:]:
        assert p.equals(pages[0]), "same request returned different rows"
    assert pages[0]["a"].to_list() == sorted(pages[0]["a"].to_list())
    assert _ro_ascending_within_ties(pages[0]), pages[0]


def test_row_order_column_breaks_ties_descending():
    dataflow = create_polars_dataflow(_tie_frame())
    page = _page(dataflow, 0, 50, sort="a", sort_direction="desc", row_order_column="ro")
    assert page["a"].to_list() == sorted(page["a"].to_list(), reverse=True)
    # The user's direction applies to the sort key only; ties stay in
    # ascending row order either way.
    assert _ro_ascending_within_ties(page), page


def test_row_order_column_orders_unsorted_pages():
    dataflow = create_polars_dataflow(_tie_frame())
    assert _page(dataflow, 0, 50, row_order_column="ro")["b"].to_list() == list(range(0, 50))
    assert _page(dataflow, 50, 100, row_order_column="ro")["b"].to_list() == list(range(50, 100))


def test_row_order_column_applies_after_search():
    df = _tie_frame().with_columns(
        pl.when(pl.col("g") == 2).then(pl.lit("hit")).otherwise(pl.lit("miss")).alias("s"))
    dataflow = create_polars_dataflow(df)
    page = _page(dataflow, 0, 50, search_string="hit", row_order_column="ro")
    assert set(page["a"].to_list()) == {2}
    assert page["b"].to_list() == sorted(page["b"].to_list())
