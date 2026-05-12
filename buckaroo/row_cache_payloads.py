"""Server-side response builders for the rowid-keyed row cache.

See docs/smart-row-cache-redesign.md. Three response kinds, all
parquet bytes:

  - populate(tagged, start, end)               → rowids + data cols
  - sort(tagged, sort_col, ascending)          → rowids only, in sort order
  - filter(already_filtered_tagged_expression) → rowids only

``tag_with_rowids(source)`` is a one-time call at widget init: it
materialises the source (xorq lazy → pa.Table), appends a dense
``_buckaroo_rowid`` column starting at 0, and re-wraps as a memtable so
the rest of the pipeline can keep operating on a stable in-memory
expression. The rowid column is ``int32`` so it matches the JS
``Int32Array`` view permutations on the wire.
"""

from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as pq
import xorq.api as xo


_ROWID_COL = "_buckaroo_rowid"


def tag_with_rowids(source: "xo.Expr") -> "xo.Expr":
    """Materialise ``source`` and append a stable rowid column.

    Returns an xorq Table backed by an in-memory pyarrow Table with a
    new ``_buckaroo_rowid`` column 0..N-1 (int32, to match the JS
    Int32Array view permutations on the wire). Repeated evaluations
    return the same rowids in the same order. Raises ``ValueError`` if
    ``source`` already exposes a ``_buckaroo_rowid`` column — callers
    must not call ``tag_with_rowids`` twice.
    """
    table = source.to_pyarrow()
    if _ROWID_COL in table.schema.names:
        raise ValueError(
            f"source already has a {_ROWID_COL!r} column; "
            "tag_with_rowids must be called exactly once per source"
        )
    rowids = pa.array(range(table.num_rows), type=pa.int32())
    tagged = table.append_column(_ROWID_COL, rowids)
    return xo.memtable(tagged)


def make_populate_payload(tagged, start: int, end: int) -> bytes:
    """Bounded-window populate response: ``[start, end)`` rows with all
    columns including ``_buckaroo_rowid``. Parquet-encoded.
    """
    windowed = tagged.limit(end - start, offset=start)
    table = windowed.to_pyarrow()
    buf = BytesIO()
    pq.write_table(table, buf, compression="none")
    return buf.getvalue()


def make_sort_payload(tagged, sort_col: str, ascending: bool = True) -> bytes:
    """Sort response: just the ``_buckaroo_rowid`` column in sort order.

    The client sees the full permutation (rowidOrder). Row contents
    are not shipped — they're either already in the RowStore or fetched
    on a follow-up ``populate`` call.
    """
    col = tagged[sort_col]
    ordered = tagged.order_by(col.asc() if ascending else col.desc())
    rowid_only = ordered.select(_ROWID_COL)
    table = rowid_only.to_pyarrow()
    buf = BytesIO()
    pq.write_table(table, buf, compression="none")
    return buf.getvalue()


def make_filter_payload(filtered_expr) -> bytes:
    """Filter response: just the ``_buckaroo_rowid`` column of the rows
    that satisfy the (already-applied) filter.

    The caller composes the filter on the tagged expression and hands
    the result here. Keeps this function predicate-agnostic. Result
    order is whatever the backend produces — the client treats this as
    a subset, so the client must not rely on source order being
    preserved.
    """
    rowid_only = filtered_expr.select(_ROWID_COL)
    table = rowid_only.to_pyarrow()
    buf = BytesIO()
    pq.write_table(table, buf, compression="none")
    return buf.getvalue()
