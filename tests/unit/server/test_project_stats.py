"""Tests for ``load_project_stat_klasses`` — scan a project's
``stats/<name>.py`` directory, exec each file with restricted globals,
return ``@stat()``-decorated callables that drop into the same
``XORQ_STATS_V2`` list the built-in xorq stats live in.

The feature lets a host (e.g. pydata-app's MCP server) hand buckaroo
runtime-authored summary stats without restarting the server or adding
new wire shapes. The function in each file is named ``compute`` and
takes one positional argument (the column expression).
"""
from __future__ import annotations

from pathlib import Path

import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.server.xorq_loading import load_project_stat_klasses  # noqa: E402


def test_returns_empty_when_stats_dir_missing(tmp_path: Path):
    assert load_project_stat_klasses(tmp_path) == []


def test_returns_empty_when_stats_dir_empty(tmp_path: Path):
    (tmp_path / "stats").mkdir()
    assert load_project_stat_klasses(tmp_path) == []


def test_picks_up_one_stat_keyed_by_filename(tmp_path: Path):
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "percent_aa.py").write_text(
        "def compute(col):\n"
        "    return col.cast('string').contains('aa').sum() / col.count()\n")
    klasses = load_project_stat_klasses(tmp_path)
    assert len(klasses) == 1
    # The wrapped function carries the filename stem as its stat name.
    assert klasses[0]._stat_func.name == "percent_aa"


def test_skips_file_without_compute(tmp_path: Path):
    """A .py file that doesn't define compute() is skipped, not raised —
    one bad file shouldn't block the rest of the stats from loading."""
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "no_compute.py").write_text("x = 42\n")
    (stats / "n_rows.py").write_text("def compute(col): return col.count()\n")

    klasses = load_project_stat_klasses(tmp_path)
    names = sorted(k._stat_func.name for k in klasses)
    assert names == ["n_rows"]


def test_skips_file_that_tries_to_import(tmp_path: Path):
    """Restricted globals strip __builtins__ so ``import os`` (which
    resolves through ``__import__``) fails at exec. The file is logged
    and skipped; the rest of the dir loads."""
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "evil.py").write_text(
        "import os\n"
        "def compute(col): return col.count()\n")
    (stats / "n_rows.py").write_text("def compute(col): return col.count()\n")

    klasses = load_project_stat_klasses(tmp_path)
    names = sorted(k._stat_func.name for k in klasses)
    assert names == ["n_rows"]


def test_skips_underscore_prefixed_files(tmp_path: Path):
    """Files starting with ``_`` (e.g. _disabled, _helpers) are not
    treated as active stats — they let users park work-in-progress
    without removing it from the project."""
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "_disabled.py").write_text("def compute(col): return col.count()\n")
    (stats / "n_rows.py").write_text("def compute(col): return col.count()\n")

    klasses = load_project_stat_klasses(tmp_path)
    names = sorted(k._stat_func.name for k in klasses)
    assert names == ["n_rows"]


def test_loaded_stat_executes_against_an_ibis_column(tmp_path: Path):
    """End-to-end: the wrapped function, called with a real ibis column,
    returns an ibis expression that executes to the expected value.
    This is the contract every stat in XORQ_STATS_V2 satisfies, and the
    proof we haven't broken it by exec'ing the source out of a file."""
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "n_rows.py").write_text("def compute(col): return col.count()\n")

    klasses = load_project_stat_klasses(tmp_path)
    assert len(klasses) == 1

    table = xo.memtable({"a": [1, 2, 3]}, name="t")
    expr = klasses[0](table["a"])
    assert int(expr.execute()) == 3


def test_dataflow_extra_klasses_extends_analysis_klasses(tmp_path: Path):
    """XorqServerDataflow's per-instance extra_klasses appends to
    _XORQ_ANALYSIS_KLASSES without mutating the class-level list.
    This is the surface the /load_expr handler uses to inject project
    stats — the test pins it so handler-only changes can't silently
    bypass the extension path."""
    from buckaroo.server.xorq_loading import (
        XorqServerDataflow, _XORQ_ANALYSIS_KLASSES)

    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "n_rows.py").write_text("def compute(col): return col.count()\n")
    extra = load_project_stat_klasses(tmp_path)
    assert len(extra) == 1

    expr = xo.memtable({"a": [1, 2, 3]}, name="t")
    dataflow = XorqServerDataflow(expr, skip_main_serial=True, extra_klasses=extra)

    # Instance attr extends; class attr untouched.
    assert dataflow.analysis_klasses is not _XORQ_ANALYSIS_KLASSES
    assert len(dataflow.analysis_klasses) == len(_XORQ_ANALYSIS_KLASSES) + 1
    assert extra[0] in dataflow.analysis_klasses
    # All built-ins still there.
    for builtin in _XORQ_ANALYSIS_KLASSES:
        assert builtin in dataflow.analysis_klasses


def test_dataflow_without_extra_klasses_keeps_class_default(tmp_path: Path):
    """No extra_klasses → instance falls back to the class-level
    _XORQ_ANALYSIS_KLASSES (the existing behaviour, must not regress)."""
    from buckaroo.server.xorq_loading import (
        XorqServerDataflow, _XORQ_ANALYSIS_KLASSES)

    expr = xo.memtable({"a": [1, 2, 3]}, name="t")
    dataflow = XorqServerDataflow(expr, skip_main_serial=True)
    assert dataflow.analysis_klasses is _XORQ_ANALYSIS_KLASSES
