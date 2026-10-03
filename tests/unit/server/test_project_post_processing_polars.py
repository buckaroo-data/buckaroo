"""Tests for ``load_project_polars_post_processing_klasses`` — scan a
project's ``post_processing/polars/<name>.py`` directory, exec each file
with restricted globals, return ``ColAnalysis`` subclasses that drop into
the same ``analysis_klasses`` channel ``filter_analysis(...,
"post_processing_method")`` walks.

The polars counterpart of ``test_project_post_processing.py`` (#994). The
function in each file is named ``process`` and takes one positional
argument, a ``pl.DataFrame``, returning a ``pl.DataFrame``; the xorq
contract (``process(expr)``) stays in ``post_processing/*.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from buckaroo.server.project_loading import (  # noqa: E402
    load_project_polars_post_processing_klasses)


def _write_pp(root: Path, name: str, source: str) -> Path:
    pp = root / "post_processing" / "polars"
    pp.mkdir(parents=True, exist_ok=True)
    path = pp / f"{name}.py"
    path.write_text(source)
    return path


def test_returns_empty_when_post_processing_dir_missing(tmp_path: Path):
    assert load_project_polars_post_processing_klasses(tmp_path) == []


def test_returns_empty_when_polars_dir_missing(tmp_path: Path):
    (tmp_path / "post_processing").mkdir()
    assert load_project_polars_post_processing_klasses(tmp_path) == []


def test_picks_up_one_post_processing_keyed_by_filename(tmp_path: Path):
    _write_pp(tmp_path, "head_three", "def process(df):\n    return df.head(3)\n")
    klasses = load_project_polars_post_processing_klasses(tmp_path)
    assert len(klasses) == 1
    assert klasses[0].post_processing_method == "head_three"


def test_ignores_xorq_post_processing_in_parent_dir(tmp_path: Path):
    (tmp_path / "post_processing").mkdir()
    (tmp_path / "post_processing" / "xorq_only.py").write_text(
        "def process(expr): return expr.limit(3)\n")
    _write_pp(tmp_path, "head_three", "def process(df): return df.head(3)\n")
    names = sorted(k.post_processing_method
        for k in load_project_polars_post_processing_klasses(tmp_path))
    assert names == ["head_three"]


def test_skips_file_without_process(tmp_path: Path):
    _write_pp(tmp_path, "no_process", "x = 42\n")
    _write_pp(tmp_path, "head_three", "def process(df): return df.head(3)\n")
    names = sorted(k.post_processing_method
        for k in load_project_polars_post_processing_klasses(tmp_path))
    assert names == ["head_three"]


def test_skips_file_that_tries_to_import(tmp_path: Path):
    _write_pp(tmp_path, "evil", "import os\ndef process(df): return df\n")
    _write_pp(tmp_path, "head_three", "def process(df): return df.head(3)\n")
    names = sorted(k.post_processing_method
        for k in load_project_polars_post_processing_klasses(tmp_path))
    assert names == ["head_three"]


def test_skips_underscore_prefixed_files(tmp_path: Path):
    _write_pp(tmp_path, "_disabled", "def process(df): return df\n")
    _write_pp(tmp_path, "head_three", "def process(df): return df.head(3)\n")
    names = sorted(k.post_processing_method
        for k in load_project_polars_post_processing_klasses(tmp_path))
    assert names == ["head_three"]


def test_loaded_post_processing_executes_against_a_polars_frame(tmp_path: Path):
    _write_pp(tmp_path, "head_two", "def process(df): return df.head(2)\n")
    klasses = load_project_polars_post_processing_klasses(tmp_path)
    assert len(klasses) == 1

    new_df, extra = klasses[0].post_process_df(pl.DataFrame({"a": [1, 2, 3, 4, 5]}))
    assert extra == {}
    assert isinstance(new_df, pl.DataFrame)
    assert len(new_df) == 2


def test_loaded_post_processing_sees_polars_module(tmp_path: Path):
    _write_pp(tmp_path, "big_only", "def process(df): return df.filter(pl.col('a') > 3)\n")
    klasses = load_project_polars_post_processing_klasses(tmp_path)
    new_df, _extra = klasses[0].post_process_df(pl.DataFrame({"a": [1, 2, 3, 4, 5]}))
    assert new_df["a"].to_list() == [4, 5]


def test_loaded_post_processing_can_use_module_level_constant(tmp_path: Path):
    _write_pp(tmp_path, "head_n", "N = 2\ndef process(df): return df.head(N)\n")
    klasses = load_project_polars_post_processing_klasses(tmp_path)
    new_df, _extra = klasses[0].post_process_df(pl.DataFrame({"a": [1, 2, 3, 4, 5]}))
    assert len(new_df) == 2


def test_loaded_post_processing_can_use_module_level_helper(tmp_path: Path):
    _write_pp(tmp_path, "head_double",
        "def _double(x):\n    return x * 2\ndef process(df): return df.head(_double(2))\n")
    klasses = load_project_polars_post_processing_klasses(tmp_path)
    new_df, _extra = klasses[0].post_process_df(pl.DataFrame({"a": [1, 2, 3, 4, 5]}))
    assert len(new_df) == 4


def test_dataflow_extra_klasses_includes_post_processing(tmp_path: Path):
    from buckaroo.server.data_loading_polars import PolarsServerDataflow

    _write_pp(tmp_path, "head_three", "def process(df): return df.head(3)\n")
    extra = load_project_polars_post_processing_klasses(tmp_path)
    assert len(extra) == 1

    dataflow = PolarsServerDataflow(
        pl.DataFrame({"a": [1, 2, 3, 4, 5]}), skip_main_serial=True, extra_klasses=extra)
    assert "head_three" in dataflow.post_processing_klasses
    assert "head_three" in dataflow.buckaroo_options["post_processing"]


def test_dataflow_actually_applies_project_post_processing(tmp_path: Path):
    """Set ``post_processing_method`` on a ``PolarsServerDataflow`` built
    with the loaded klasses and ``processed_df`` reflects ``process()``."""
    from buckaroo.server.data_loading_polars import PolarsServerDataflow

    _write_pp(tmp_path, "head_two", "def process(df): return df.head(2)\n")
    extra = load_project_polars_post_processing_klasses(tmp_path)

    dataflow = PolarsServerDataflow(
        pl.DataFrame({"a": [1, 2, 3, 4, 5]}), skip_main_serial=True, extra_klasses=extra)
    dataflow.post_processing_method = "head_two"
    assert len(dataflow.processed_df) == 2
    assert dataflow.df_meta["filtered_rows"] == 2
