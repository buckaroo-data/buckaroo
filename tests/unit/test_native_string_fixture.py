"""Drift check for the native-parquet string-cell JS fixture.

The committed fixture under
``packages/buckaroo-js-core/.../native_string_cells_parquet.json`` is what
the ``nativeStringCells.test.ts`` regression test reads. Regenerate it with::

    uv run python scripts/generate_native_string_fixture.py

This test re-runs the generator in memory and diffs the parquet bytes plus
the pyarrow ground-truth decode against the committed copy, so a wire-format
change without a fixture refresh surfaces on CI. It also documents the
intent: every encoded cell is a JSON-looking *string*, and the ground-truth
decode keeps it a string.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("polars")
pytest.importorskip("xorq.api")

from scripts.generate_native_string_fixture import (  # noqa: E402
    FIXTURE_PATH, generate)


def test_committed_fixture_matches_in_memory_regeneration():
    assert FIXTURE_PATH.exists(), (
        f"fixture missing at {FIXTURE_PATH}; "
        "run scripts/generate_native_string_fixture.py")
    on_disk = json.loads(FIXTURE_PATH.read_text())
    fresh = generate()

    for backend in ("polars", "xorq"):
        od = on_disk["backends"][backend]
        fr = fresh["backends"][backend]
        assert od["expected"] == fr["expected"], (
            f"{backend} ground-truth decode drifted; regenerate with "
            "scripts/generate_native_string_fixture.py")
        # Deterministic for the same input + same polars/pyarrow version.
        assert od["data"] == fr["data"], (
            f"{backend} parquet bytes drifted; regenerate with "
            "scripts/generate_native_string_fixture.py")
        assert od["envelope"] == fr["envelope"], (
            f"{backend} transport envelope drifted; regenerate with "
            "scripts/generate_native_string_fixture.py")


def test_native_senders_stamp_empty_json_columns():
    """The native paths must declare json_columns: [] on the wire so the JS
    decoder skips the fastparquet-style JSON.parse. This is the producer half
    of the contract nativeStringCells.test.ts checks on the decoder half."""
    payload = generate()
    for backend in ("polars", "xorq"):
        env = payload["backends"][backend]["envelope"]
        assert env["format"] == "parquet_buffer"
        assert env.get("json_columns") == [], (
            f"{backend} sender must stamp json_columns: [], got "
            f"{env.get('json_columns')!r}")


def test_ground_truth_keeps_json_looking_strings_as_strings():
    """The whole point: these cells are strings on the wire and must stay
    strings — pyarrow (and, post-fix, decodeDFData) never JSON-parses them."""
    payload = generate()
    for backend in ("polars", "xorq"):
        row0 = payload["backends"][backend]["expected"][0]
        assert row0["b"] == "null"
        assert row0["c"] == "true"
        assert row0["d"] == "123"
        assert row0["e"] == '{"a": 1}'
        assert row0["f"] == "[1, 2]"
        for col in ("b", "c", "d", "e", "f"):
            assert isinstance(row0[col], str), (
                f"{backend} cell {col} should be a str, got {type(row0[col])}")
