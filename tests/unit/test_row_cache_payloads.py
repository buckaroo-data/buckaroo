"""Phase 6 — server-side payload builders for the new row cache.

Tested in isolation (no widget, no anywidget plumbing). The builders take
an xorq expression and return parquet bytes shaped for the new
client-side cache layer:

  populate → bytes carrying {_buckaroo_rowid + data columns} for [start, end)
  sort     → bytes carrying just _buckaroo_rowid in sort order (rowidOrder)
  filter   → bytes carrying just _buckaroo_rowid for matching rows (rowidSubset)

Phase 7 wires these into the widget; phase 6 just establishes the wire shape.
"""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

xo = pytest.importorskip("xorq.api")


def _read_parquet_bytes(b: bytes) -> pa.Table:
    return pq.read_table(pa.BufferReader(b))


def _make_source():
    return xo.memtable(
        {
            "name": ["alice", "bob", "carol", "dave", "eve"],
            "age": [30, 25, 40, 35, 28],
        }
    )


class TestTagWithRowids:
    def test_adds_a_dense_rowid_column_starting_at_zero(self):
        from buckaroo.row_cache_payloads import tag_with_rowids

        tagged = tag_with_rowids(_make_source())
        table = tagged.to_pyarrow()
        rowids = table["_buckaroo_rowid"].to_pylist()
        assert rowids == [0, 1, 2, 3, 4]

    def test_rowid_assignment_is_stable_across_repeated_evaluations(self):
        # The whole point — a rowid emitted by populate at t=0 must
        # match the rowid emitted by sort or filter at t=1.
        from buckaroo.row_cache_payloads import tag_with_rowids

        tagged = tag_with_rowids(_make_source())
        a = tagged.to_pyarrow()["_buckaroo_rowid"].to_pylist()
        b = tagged.to_pyarrow()["_buckaroo_rowid"].to_pylist()
        assert a == b

    def test_preserves_the_data_columns(self):
        from buckaroo.row_cache_payloads import tag_with_rowids

        tagged = tag_with_rowids(_make_source())
        cols = tagged.schema().names
        assert "name" in cols
        assert "age" in cols
        assert "_buckaroo_rowid" in cols


class TestMakePopulatePayload:
    def test_returns_parquet_with_rowids_and_data_columns(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_populate_payload,
        )

        tagged = tag_with_rowids(_make_source())
        b = make_populate_payload(tagged, 0, 3)
        table = _read_parquet_bytes(b)
        assert table.num_rows == 3
        assert table["_buckaroo_rowid"].to_pylist() == [0, 1, 2]
        assert table["name"].to_pylist() == ["alice", "bob", "carol"]

    def test_offset_window_carries_the_correct_rowids(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_populate_payload,
        )

        tagged = tag_with_rowids(_make_source())
        b = make_populate_payload(tagged, 2, 5)
        table = _read_parquet_bytes(b)
        assert table.num_rows == 3
        assert table["_buckaroo_rowid"].to_pylist() == [2, 3, 4]

    def test_request_past_end_returns_whatever_rows_exist(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_populate_payload,
        )

        tagged = tag_with_rowids(_make_source())
        b = make_populate_payload(tagged, 3, 100)
        table = _read_parquet_bytes(b)
        # 5-row source, asked from 3 → got 2
        assert table.num_rows == 2
        assert table["_buckaroo_rowid"].to_pylist() == [3, 4]


class TestMakeSortPayload:
    def test_returns_rowid_column_in_ascending_sort_order(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_sort_payload,
        )

        # age: alice=30, bob=25, carol=40, dave=35, eve=28
        # rowids:        0       1       2        3       4
        # asc by age → rowids in order: 1, 4, 0, 3, 2
        tagged = tag_with_rowids(_make_source())
        b = make_sort_payload(tagged, "age", ascending=True)
        table = _read_parquet_bytes(b)
        assert table.schema.names == ["_buckaroo_rowid"]
        assert table["_buckaroo_rowid"].to_pylist() == [1, 4, 0, 3, 2]

    def test_returns_rowid_column_in_descending_sort_order(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_sort_payload,
        )

        tagged = tag_with_rowids(_make_source())
        b = make_sort_payload(tagged, "age", ascending=False)
        table = _read_parquet_bytes(b)
        assert table["_buckaroo_rowid"].to_pylist() == [2, 3, 0, 4, 1]

    def test_carries_no_data_columns(self):
        # Sort response is just the permutation; rows are already in the
        # client's RowStore (or fetched on follow-up populate).
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_sort_payload,
        )

        tagged = tag_with_rowids(_make_source())
        b = make_sort_payload(tagged, "name", ascending=True)
        table = _read_parquet_bytes(b)
        assert table.schema.names == ["_buckaroo_rowid"]


class TestMakeFilterPayload:
    def test_returns_rowid_column_for_filtered_subset(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_filter_payload,
        )

        tagged = tag_with_rowids(_make_source())
        # age > 30 → carol (rowid 2), dave (rowid 3)
        filtered = tagged.filter(tagged.age > 30)
        b = make_filter_payload(filtered)
        table = _read_parquet_bytes(b)
        assert table.schema.names == ["_buckaroo_rowid"]
        # Result order doesn't matter for a filter — the client treats
        # this as a subset. Sort for stability.
        assert sorted(table["_buckaroo_rowid"].to_pylist()) == [2, 3]

    def test_empty_filter_returns_zero_rows(self):
        from buckaroo.row_cache_payloads import (
            tag_with_rowids,
            make_filter_payload,
        )

        tagged = tag_with_rowids(_make_source())
        filtered = tagged.filter(tagged.age > 1000)
        b = make_filter_payload(filtered)
        table = _read_parquet_bytes(b)
        assert table.num_rows == 0
        assert table.schema.names == ["_buckaroo_rowid"]
