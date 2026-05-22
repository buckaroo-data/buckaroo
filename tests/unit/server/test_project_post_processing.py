"""Tests for ``load_project_post_processing_klasses`` — scan a project's
``post_processing/<name>.py`` directory, exec each file with restricted
globals, return ``ColAnalysis`` subclasses that drop into the same
``analysis_klasses`` channel ``filter_analysis(..., "post_processing_method")``
walks to populate ``post_processing_klasses``.

The feature lets a host (e.g. pydata-app's MCP server) hand buckaroo
runtime-authored post-processing functions without restarting the
server or adding a new wire shape. The function in each file is named
``process`` and takes one positional argument (the cleaned expression).

Mirrors ``test_project_stats.py`` for the post-processing channel.
"""
from __future__ import annotations

from pathlib import Path

import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.server.xorq_loading import (  # noqa: E402
    load_project_post_processing_klasses)


def test_returns_empty_when_post_processing_dir_missing(tmp_path: Path):
    assert load_project_post_processing_klasses(tmp_path) == []


def test_returns_empty_when_post_processing_dir_empty(tmp_path: Path):
    (tmp_path / "post_processing").mkdir()
    assert load_project_post_processing_klasses(tmp_path) == []


def test_picks_up_one_post_processing_keyed_by_filename(tmp_path: Path):
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "head_three.py").write_text(
        "def process(expr):\n"
        "    return expr.limit(3)\n")
    klasses = load_project_post_processing_klasses(tmp_path)
    assert len(klasses) == 1
    # The wrapped class carries the filename stem as its
    # post_processing_method — the key filter_analysis builds the
    # post_processing_klasses map with.
    assert klasses[0].post_processing_method == "head_three"


def test_skips_file_without_process(tmp_path: Path):
    """A .py file that doesn't define process() is skipped, not raised —
    one bad file shouldn't block the rest of the post-processors from
    loading."""
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "no_process.py").write_text("x = 42\n")
    (pp / "head_three.py").write_text(
        "def process(expr): return expr.limit(3)\n")

    klasses = load_project_post_processing_klasses(tmp_path)
    names = sorted(k.post_processing_method for k in klasses)
    assert names == ["head_three"]


def test_skips_file_that_tries_to_import(tmp_path: Path):
    """Restricted globals strip __builtins__ so ``import os`` (which
    resolves through ``__import__``) fails at exec. The file is logged
    and skipped; the rest of the dir loads. Matches the stat loader's
    sandbox posture."""
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "evil.py").write_text(
        "import os\n"
        "def process(expr): return expr\n")
    (pp / "head_three.py").write_text(
        "def process(expr): return expr.limit(3)\n")

    klasses = load_project_post_processing_klasses(tmp_path)
    names = sorted(k.post_processing_method for k in klasses)
    assert names == ["head_three"]


def test_skips_underscore_prefixed_files(tmp_path: Path):
    """Files starting with ``_`` (e.g. _disabled, _helpers) are not
    treated as active post-processors — they let users park work-in-
    progress without removing it from the project."""
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "_disabled.py").write_text(
        "def process(expr): return expr\n")
    (pp / "head_three.py").write_text(
        "def process(expr): return expr.limit(3)\n")

    klasses = load_project_post_processing_klasses(tmp_path)
    names = sorted(k.post_processing_method for k in klasses)
    assert names == ["head_three"]


def test_loaded_post_processing_executes_against_an_ibis_expression(tmp_path: Path):
    """End-to-end on the wrapped class: calling ``post_process_df`` with
    a real ibis expression returns the transformed expression (or
    DataFrame). This is the contract every entry in
    ``post_processing_klasses`` satisfies."""
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "head_two.py").write_text(
        "def process(expr): return expr.limit(2)\n")

    klasses = load_project_post_processing_klasses(tmp_path)
    assert len(klasses) == 1

    table = xo.memtable({"a": [1, 2, 3, 4, 5]}, name="t")
    new_expr, extra = klasses[0].post_process_df(table)
    # extra_conf dict shape matches DecoratedXorqProcessing in
    # xorq_buckaroo.py:209 — empty by default.
    assert extra == {}
    assert int(new_expr.count().execute()) == 2


def test_loaded_post_processing_can_use_module_level_constant(tmp_path: Path):
    """A module-level constant defined in the post-processing file must
    be visible to ``process()`` when it runs. Same Codex P1 the stat
    loader hits: separate globals/locals dicts at exec time put top-
    level assignments into locals while ``process`` captures globals
    as its ``__globals__`` — every call would NameError."""
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "head_n.py").write_text(
        "N = 2\n"
        "def process(expr): return expr.limit(N)\n")

    klasses = load_project_post_processing_klasses(tmp_path)
    assert len(klasses) == 1

    table = xo.memtable({"a": [1, 2, 3, 4, 5]}, name="t")
    new_expr, _extra = klasses[0].post_process_df(table)
    assert int(new_expr.count().execute()) == 2


def test_loaded_post_processing_can_use_module_level_helper(tmp_path: Path):
    """Same Codex P1 in helper-function form: a top-level ``def`` in
    the post-processing file must be callable from ``process()``."""
    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "head_double.py").write_text(
        "def _double(x):\n"
        "    return x * 2\n"
        "def process(expr): return expr.limit(_double(2))\n")

    klasses = load_project_post_processing_klasses(tmp_path)
    assert len(klasses) == 1

    table = xo.memtable({"a": [1, 2, 3, 4, 5]}, name="t")
    new_expr, _extra = klasses[0].post_process_df(table)
    assert int(new_expr.count().execute()) == 4


def test_dataflow_extra_klasses_includes_post_processing(tmp_path: Path):
    """Project post-processing classes injected via XorqServerDataflow's
    extra_klasses appear in ``post_processing_klasses`` (the dict the
    dataflow's ``_compute_processed_result`` looks the method up in)
    and in ``buckaroo_options['post_processing']`` (the list the UI
    populates the dropdown from)."""
    from buckaroo.server.xorq_loading import XorqServerDataflow

    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "head_three.py").write_text(
        "def process(expr): return expr.limit(3)\n")
    extra = load_project_post_processing_klasses(tmp_path)
    assert len(extra) == 1

    expr = xo.memtable({"a": [1, 2, 3, 4, 5]}, name="t")
    dataflow = XorqServerDataflow(
        expr, skip_main_serial=True, extra_klasses=extra)

    assert "head_three" in dataflow.post_processing_klasses
    assert "head_three" in dataflow.buckaroo_options["post_processing"]


def test_dataflow_actually_applies_project_post_processing(tmp_path: Path):
    """End-to-end through the dataflow: set
    ``post_processing_method = "<stem>"`` on an XorqServerDataflow
    constructed with the loaded project klasses, and ``processed_df``
    reflects the file's ``process()`` transformation. This is the
    handler-to-pipeline path the feature exists to enable."""
    from buckaroo.server.xorq_loading import XorqServerDataflow

    pp = tmp_path / "post_processing"
    pp.mkdir()
    (pp / "head_two.py").write_text(
        "def process(expr): return expr.limit(2)\n")
    extra = load_project_post_processing_klasses(tmp_path)

    expr = xo.memtable({"a": [1, 2, 3, 4, 5]}, name="t")
    dataflow = XorqServerDataflow(
        expr, skip_main_serial=True, extra_klasses=extra)
    dataflow.post_processing_method = "head_two"

    # processed_df is what window_to_parquet / handle_infinite_request_xorq
    # read; if the post-processor is wired in correctly, the row count
    # drops from 5 to 2.
    assert int(dataflow.processed_df.count().execute()) == 2
