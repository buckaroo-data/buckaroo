"""Regenerate the JS-side fixture proving native-parquet string cells
survive ``decodeDFData`` without being JSON-parsed into the wrong type.

Background: the polars / xorq / lazy infinite paths write *native* parquet
UTF8 strings (``df.write_parquet`` / ``pq.write_table``), unlike the pandas
path which JSON-encodes object cells via fastparquet. The unified JS decoder
``decodeDFData`` runs every ``parquet_buffer`` frame through
``parseParquetRow``, which JSON-parses every string cell. For native-parquet
backends that corrupts any string whose text happens to be valid JSON
(``"null"`` -> null, ``"123"`` -> 123, ``'{"a": 1}'`` -> object).

This fixture captures the exact bytes both backends emit for a DataFrame full
of such "JSON-looking" strings, plus the ground-truth decode read straight
back through pyarrow (the strings, unchanged). The JS test in
``nativeStringCells.test.ts`` decodes the same bytes through ``decodeDFData``
and asserts it matches the ground truth.

Run when the wire format changes:

    uv run python scripts/generate_native_string_fixture.py

The companion test ``tests/unit/test_native_string_fixture.py`` re-runs the
generator in memory and diffs it against the committed copy, so drift surfaces
on the next CI run.
"""
from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import polars as pl
import pyarrow.parquet as pq
import xorq.api as xo

from buckaroo.polars_buckaroo import to_parquet as polars_to_parquet
from buckaroo.xorq_buckaroo import XorqBuckarooInfiniteWidget

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT
    / "packages/buckaroo-js-core/src/components/DFViewerParts/test-fixtures/native_string_cells_parquet.json")

# Every data cell is a *string*. Each column targets a different JSON literal
# that parseParquetRow's unconditional JSON.parse would silently coerce:
#   norm -> plain word (parse throws, stays string — the control)
#   jnull/jbool/jint -> parse to null / boolean / number
#   jobj/jarr -> parse to object / array
_DATA = {
    "norm": ["alpha", "beta"],
    "jnull": ["null", "value"],
    "jbool": ["true", "false"],
    "jint": ["123", "45"],
    "jobj": ['{"a": 1}', '{"b": 2}'],
    "jarr": ["[1, 2]", "[3]"],
}


def _rows_from_parquet(parquet_bytes: bytes) -> List[Dict[str, Any]]:
    """Ground-truth decode: read the native bytes straight back through
    pyarrow. Every string cell comes back as the exact string written —
    this is what decodeDFData must also produce."""
    table = pq.read_table(BytesIO(parquet_bytes))
    rows = table.to_pylist()
    # hyparquet hands the JS side INT64 as Number for the index column;
    # mirror that so the committed `expected` matches what JS asserts.
    for row in rows:
        if "index" in row and row["index"] is not None:
            row["index"] = int(row["index"])
    return rows


def _polars_bytes() -> bytes:
    # polars_buckaroo.to_parquet requires an explicit 'index' column and
    # rewrites the other columns to the a, b, c... space.
    df = pl.DataFrame({"index": [0, 1], **_DATA})
    return polars_to_parquet(df)


def _xorq_bytes() -> bytes:
    # Drive the real XorqBuckarooInfiniteWidget infinite path, capturing the
    # parquet buffer it emits — same harness as generate_xorq_window_fixture.
    expr = xo.memtable(_DATA)
    widget = XorqBuckarooInfiniteWidget(expr)
    sent: list = []
    widget.send = lambda msg, buffers=None: sent.append((msg, buffers))
    widget._handle_payload_args({"start": 0, "end": len(_DATA["norm"])})
    if not sent or not sent[0][1]:
        raise RuntimeError("xorq widget emitted no parquet buffer")
    return sent[0][1][0]


def generate() -> Dict[str, Any]:
    """Build the fixture payload — captured bytes plus the pyarrow ground
    truth for each backend. No file I/O."""
    polars_bytes = _polars_bytes()
    xorq_bytes = _xorq_bytes()
    return {
        "description": (
            "Native parquet string cells whose text is valid JSON. "
            "decodeDFData must return them unchanged, not JSON.parse them."),
        "backends": {
            "polars": {
                "data": base64.b64encode(polars_bytes).decode("ascii"),
                "expected": _rows_from_parquet(polars_bytes),
            },
            "xorq": {
                "data": base64.b64encode(xorq_bytes).decode("ascii"),
                "expected": _rows_from_parquet(xorq_bytes),
            },
        },
    }


def write() -> None:
    payload = generate()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    for name, blob in payload["backends"].items():
        print(f"  {name}: {len(blob['data'])} chars b64, "
              f"{len(blob['expected'])} rows")
    print(f"wrote {FIXTURE_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    write()
