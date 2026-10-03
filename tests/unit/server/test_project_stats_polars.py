"""Tests for ``load_project_polars_stat_klasses`` — scan a project's
``stats/polars/<name>.py`` directory, exec each file with restricted
globals, return ``@stat()``-decorated callables that drop into the same
``PL_ANALYSIS_V2`` list the built-in polars stats live in.

The polars counterpart of ``test_project_stats.py`` (#994). The engine a
stat file is written for is picked by its directory: ``stats/*.py`` is the
xorq contract (``compute(col)`` returning an ibis expression), while
``stats/polars/*.py`` is ``compute(ser)`` taking a ``pl.Series`` and
returning a plain value, wrapped with the ``RawSeries`` marker that the
built-in polars stats use.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from buckaroo.pluggable_analysis_framework.stat_func import RawSeries  # noqa: E402
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline  # noqa: E402
from buckaroo.server.project_loading import load_project_polars_stat_klasses  # noqa: E402


def _write_stat(root: Path, name: str, source: str) -> Path:
    stats = root / "stats" / "polars"
    stats.mkdir(parents=True, exist_ok=True)
    path = stats / f"{name}.py"
    path.write_text(source)
    return path


def _run(klasses, df):
    sdf, errors = StatPipeline(klasses, unit_test=False).process_df(df)
    assert errors == []
    return sdf


def test_returns_empty_when_stats_dir_missing(tmp_path: Path):
    assert load_project_polars_stat_klasses(tmp_path) == []


def test_returns_empty_when_polars_dir_missing(tmp_path: Path):
    """``stats/`` alone is the xorq directory; without ``stats/polars/``
    there is nothing for the polars loader."""
    (tmp_path / "stats").mkdir()
    assert load_project_polars_stat_klasses(tmp_path) == []


def test_picks_up_one_stat_keyed_by_filename(tmp_path: Path):
    _write_stat(tmp_path, "n_rows", "def compute(ser):\n    return ser.len()\n")
    klasses = load_project_polars_stat_klasses(tmp_path)
    assert len(klasses) == 1
    sf = klasses[0]._stat_func
    assert sf.name == "n_rows"
    # The single parameter is marked RawSeries so the pipeline hands the
    # function the column itself, whatever the parameter was called.
    assert sf.needs_raw
    assert [r.type for r in sf.requires] == [RawSeries]


def test_ignores_xorq_stats_in_parent_dir(tmp_path: Path):
    """A file in ``stats/`` (the xorq contract) is not a polars stat: the
    loaders never guess an engine from a file's contents."""
    (tmp_path / "stats").mkdir()
    (tmp_path / "stats" / "xorq_only.py").write_text(
        "def compute(col): return col.count()\n")
    _write_stat(tmp_path, "n_rows", "def compute(ser): return ser.len()\n")
    names = sorted(k._stat_func.name for k in load_project_polars_stat_klasses(tmp_path))
    assert names == ["n_rows"]


def test_skips_file_without_compute(tmp_path: Path):
    _write_stat(tmp_path, "no_compute", "x = 42\n")
    _write_stat(tmp_path, "n_rows", "def compute(ser): return ser.len()\n")
    names = sorted(k._stat_func.name for k in load_project_polars_stat_klasses(tmp_path))
    assert names == ["n_rows"]


def test_skips_file_that_tries_to_import(tmp_path: Path):
    """Same sandbox as the xorq loaders: ``import os`` resolves through
    ``__import__``, which the restricted builtins leave out."""
    _write_stat(tmp_path, "evil", "import os\ndef compute(ser): return ser.len()\n")
    _write_stat(tmp_path, "n_rows", "def compute(ser): return ser.len()\n")
    names = sorted(k._stat_func.name for k in load_project_polars_stat_klasses(tmp_path))
    assert names == ["n_rows"]


def test_skips_underscore_prefixed_files(tmp_path: Path):
    _write_stat(tmp_path, "_disabled", "def compute(ser): return ser.len()\n")
    _write_stat(tmp_path, "n_rows", "def compute(ser): return ser.len()\n")
    names = sorted(k._stat_func.name for k in load_project_polars_stat_klasses(tmp_path))
    assert names == ["n_rows"]


def test_loaded_stat_executes_against_a_polars_series(tmp_path: Path):
    """End-to-end through ``StatPipeline``: the wrapped function receives
    the ``pl.Series`` and its return value lands under the filename key."""
    _write_stat(tmp_path, "n_rows", "def compute(ser): return ser.len()\n")
    klasses = load_project_polars_stat_klasses(tmp_path)
    sdf = _run(klasses, pl.DataFrame({"a": [1, 2, 3]}))
    assert sdf["a"]["n_rows"] == 3


def test_loaded_stat_sees_polars_module(tmp_path: Path):
    """``pl`` is in scope so a stat can reach dtypes and expressions
    beyond bare series methods, as ``ibis``/``xorq`` are for xorq stats."""
    _write_stat(tmp_path, "is_int", "def compute(ser): return ser.dtype == pl.Int64\n")
    klasses = load_project_polars_stat_klasses(tmp_path)
    sdf = _run(klasses, pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}))
    assert sdf["a"]["is_int"] is True
    assert sdf["b"]["is_int"] is False


def test_loaded_stat_can_use_module_level_constant(tmp_path: Path):
    _write_stat(tmp_path, "above_threshold",
        "THRESHOLD = 2\ndef compute(ser): return int((ser > THRESHOLD).sum())\n")
    klasses = load_project_polars_stat_klasses(tmp_path)
    sdf = _run(klasses, pl.DataFrame({"a": [1, 2, 3]}))
    assert sdf["a"]["above_threshold"] == 1


def test_loaded_stat_can_use_module_level_helper(tmp_path: Path):
    _write_stat(tmp_path, "double_count",
        "def _double(x):\n    return x * 2\ndef compute(ser):\n    return _double(ser.len())\n")
    klasses = load_project_polars_stat_klasses(tmp_path)
    sdf = _run(klasses, pl.DataFrame({"a": [1, 2, 3]}))
    assert sdf["a"]["double_count"] == 6


def test_dataflow_extra_klasses_extends_analysis_klasses(tmp_path: Path):
    """``PolarsServerDataflow``'s per-instance ``extra_klasses`` appends
    to ``local_analysis_klasses`` without mutating it, and the project
    stat's value shows up in the dataflow's ``merged_sd``."""
    from buckaroo.polars_buckaroo import local_analysis_klasses
    from buckaroo.server.data_loading_polars import PolarsServerDataflow

    _write_stat(tmp_path, "n_rows", "def compute(ser): return ser.len()\n")
    extra = load_project_polars_stat_klasses(tmp_path)
    assert len(extra) == 1

    df = pl.DataFrame({"a": [1, 2, 3]})
    dataflow = PolarsServerDataflow(df, skip_main_serial=True, extra_klasses=extra)

    assert dataflow.analysis_klasses is not local_analysis_klasses
    assert len(dataflow.analysis_klasses) == len(local_analysis_klasses) + 1
    assert extra[0] in dataflow.analysis_klasses
    for builtin in local_analysis_klasses:
        assert builtin in dataflow.analysis_klasses
    assert dataflow.merged_sd["a"]["n_rows"] == 3


def test_dataflow_without_extra_klasses_keeps_class_default():
    from buckaroo.polars_buckaroo import local_analysis_klasses
    from buckaroo.server.data_loading_polars import PolarsServerDataflow

    dataflow = PolarsServerDataflow(pl.DataFrame({"a": [1, 2, 3]}), skip_main_serial=True)
    assert dataflow.analysis_klasses is local_analysis_klasses
