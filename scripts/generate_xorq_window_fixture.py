"""Regenerate the JS-side fixture for the xorq window-parquet
integration test.

The fixture captures the bytes that ``XorqBuckarooInfiniteWidget``
emits in response to one ``infinite_request`` — i.e. the arrow-direct
parquet payload (no pandas / no fastparquet detour). The JS test in
``packages/buckaroo-js-core/.../xorqWindow.test.ts`` reads it through
hyparquet and asserts the wire format is consumable.

Run when the wire format changes:

    uv run python scripts/generate_xorq_window_fixture.py

The companion test ``tests/unit/test_xorq_window_fixture.py`` re-runs
the generator in memory and diffs it against the committed copy, so
drift surfaces on the next CI run.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict

import xorq.api as xo

from buckaroo.xorq_buckaroo import XorqBuckarooInfiniteWidget

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT
    / "packages/buckaroo-js-core/src/components/DFViewerParts/test-fixtures/xorq_window_parquet.json")

# Deterministic input — small but exercises the columns the JS test
# wants to assert against (numeric, string, integer index column).
_DATA = {
    "price": [12.5, 18.9, 7.4, 22.1, 14.0, 9.9, 31.2, 11.5, 19.8, 50.0],
    "name": ["alpha", "beta", "gamma", "delta", "eps", "zeta", "eta", "theta", "iota", "kappa"]}
_WINDOW = {"start": 2, "end": 7}


def _capture(widget) -> bytes:
    sent: list = []
    widget.send = lambda msg, buffers=None: sent.append((msg, buffers))
    widget._handle_payload_args(_WINDOW)
    if not sent:
        raise RuntimeError("widget did not emit a parquet response")
    _msg, buffers = sent[0]
    if not buffers:
        raise RuntimeError("response had no parquet buffer")
    return buffers[0]


def generate() -> Dict[str, Any]:
    """Build the fixture payload — no I/O. Used by the regen script and
    the in-memory comparison test."""
    expr = xo.memtable(_DATA)
    widget = XorqBuckarooInfiniteWidget(expr)
    parquet_bytes = _capture(widget)
    return {
        "format": "parquet_xorq",
        "expr_columns": list(_DATA.keys()),
        # XorqBuckarooInfiniteWidget renames at the expression level
        # before to_pyarrow(), so the wire columns are in the rewritten
        # 'a, b, ...' space plus an absolute-offset 'index' column.
        "rewritten_columns": ["a", "b", "index"],
        "row_count": _WINDOW["end"] - _WINDOW["start"],
        "start": _WINDOW["start"],
        "end": _WINDOW["end"],
        "expected_names_at_offset": list(
            _DATA["name"][_WINDOW["start"]:_WINDOW["end"]]),
        "data": base64.b64encode(parquet_bytes).decode("ascii")}


def write() -> None:
    payload = generate()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {FIXTURE_PATH.relative_to(REPO_ROOT)} "
          f"({len(payload['data'])} chars b64, {payload['row_count']} rows)")


if __name__ == "__main__":
    write()
