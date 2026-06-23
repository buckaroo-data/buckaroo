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

from buckaroo.polars_buckaroo import PolarsBuckarooInfiniteWidget
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
_DATA = {"norm": ["alpha", "beta"], "jnull": ["null", "value"], "jbool": ["true", "false"], "jint": ["123", "45"],
    "jobj": ['{"a": 1}', '{"b": 2}'], "jarr": ["[1, 2]", "[3]"]}


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


def _capture_infinite_resp(widget: Any) -> tuple:
    """Drive a widget's infinite path and capture the (envelope, bytes) it
    emits. The envelope is ``msg['payload']`` — the exact transport dict the JS
    side decodes — so the fixture records whether the native sender really
    stamped ``json_columns: []``, not a hand-built assumption."""
    sent: list = []
    widget.send = lambda msg, buffers=None: sent.append((msg, buffers))
    widget._handle_payload_args({"start": 0, "end": len(_DATA["norm"])})
    if not sent or not sent[0][1]:
        raise RuntimeError(f"{type(widget).__name__} emitted no parquet buffer")
    msg, buffers = sent[0]
    return msg["payload"], buffers[0]


def _polars_envelope_bytes() -> tuple:
    # Drive the real PolarsBuckarooInfiniteWidget infinite path (df.write_parquet,
    # native UTF8 strings). The widget rewrites data columns to a, b, c... space.
    widget = PolarsBuckarooInfiniteWidget(pl.DataFrame(_DATA))
    return _capture_infinite_resp(widget)


def _xorq_envelope_bytes() -> tuple:
    # Drive the real XorqBuckarooInfiniteWidget infinite path (pq.write_table).
    widget = XorqBuckarooInfiniteWidget(xo.memtable(_DATA))
    return _capture_infinite_resp(widget)


def generate() -> Dict[str, Any]:
    """Build the fixture payload — the captured envelope + parquet bytes each
    native sender emits, plus the pyarrow ground-truth decode. No file I/O."""
    polars_env, polars_bytes = _polars_envelope_bytes()
    xorq_env, xorq_bytes = _xorq_envelope_bytes()
    return {
        "description": (
            "Native parquet string cells whose text is valid JSON. "
            "decodeDFData must return them unchanged, not JSON.parse them. The "
            "captured envelope carries json_columns: [] so the decoder skips "
            "the fastparquet-style JSON.parse for these native frames."),
        "backends": {
            "polars": {
                "envelope": polars_env,
                "data": base64.b64encode(polars_bytes).decode("ascii"),
                "expected": _rows_from_parquet(polars_bytes),
            },
            "xorq": {
                "envelope": xorq_env,
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
