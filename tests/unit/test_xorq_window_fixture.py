"""Drift check for the xorq window-parquet JS fixture.

The committed fixture under
``packages/buckaroo-js-core/.../xorq_window_parquet.json`` is what the
hyparquet integration test reads. Regenerate it with::

    uv run python scripts/generate_xorq_window_fixture.py

This test re-runs the generator in memory and diffs every field —
including the parquet bytes — against the committed copy. Catches:

- A wire-format change (different schema / encoding) without a fixture
  refresh.
- A non-deterministic write (which would force us to widen the diff).

The Python and JS sides agree on what bytes the JS hyparquet decoder
sees, which is the whole point of the fixture pattern.
"""
from __future__ import annotations

import json

import pytest

xo = pytest.importorskip("xorq.api")

from scripts.generate_xorq_window_fixture import (  # noqa: E402
    FIXTURE_PATH, generate)


def test_committed_fixture_matches_in_memory_regeneration():
    assert FIXTURE_PATH.exists(), (
        f"fixture missing at {FIXTURE_PATH}; "
        "run scripts/generate_xorq_window_fixture.py")
    on_disk = json.loads(FIXTURE_PATH.read_text())
    fresh = generate()

    # Metadata fields drift first if a config changes — diff each so the
    # failure points at the offending key.
    for key in (
        "format", "row_count", "start", "end", "rewritten_columns",
        "expr_columns", "expected_names_at_offset"):
        assert on_disk[key] == fresh[key], (
            f"fixture field {key!r} drifted: "
            f"on-disk={on_disk[key]!r} fresh={fresh[key]!r}; "
            "regenerate with scripts/generate_xorq_window_fixture.py")

    # The parquet bytes are deterministic for the same input + same
    # pyarrow version. If this drifts, regenerate the fixture.
    assert on_disk["data"] == fresh["data"], (
        "parquet bytes drifted; regenerate with "
        "scripts/generate_xorq_window_fixture.py")
