"""Tests for the ``ENGINE`` marker on project stat and post-processing
files (#994).

A project keeps its stats and post-processors in one ``stats/`` and one
``post_processing/`` directory. A file says which engine it is written
for with a module-level ``ENGINE = "polars"``; a file without the marker
is a xorq file, so projects written before the marker existed load as
they did. Each loader takes an ``engine`` argument and returns only the
files written for that engine, wrapped for that engine's pipeline:

* xorq stats are ``compute(col)`` over an ibis column, wrapped with the
  ``XorqColumn`` marker; polars stats are ``compute(ser)`` over a
  ``pl.Series``, wrapped with ``RawSeries`` like the built-in polars stats
  in ``customizations/pl_stats_v2.py``.
* xorq post-processors are ``process(expr)``; polars post-processors are
  ``process(df)`` over a ``pl.DataFrame``.

The loaders live in ``buckaroo.server.project_loading`` so the polars
``/load`` path can use them without importing xorq.
``buckaroo.server.xorq_loading`` keeps re-exporting them.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from buckaroo.pluggable_analysis_framework.stat_func import RawSeries, XorqColumn  # noqa: E402
from buckaroo.server.project_loading import (  # noqa: E402
    load_project_post_processing_klasses, load_project_stat_klasses)

XORQ_STAT = "def compute(col):\n    return col.count()\n"
POLARS_STAT = (
    "ENGINE = 'polars'\n"
    "def compute(ser):\n"
    "    return len(ser)\n")
XORQ_PP = "def process(expr):\n    return expr.limit(2)\n"
POLARS_PP = (
    "ENGINE = 'polars'\n"
    "def process(df):\n"
    "    return df.head(2)\n")


def _write(root: Path, sub: str, name: str, source: str) -> None:
    (root / sub).mkdir(exist_ok=True)
    (root / sub / name).write_text(source)


def _stat_names(klasses) -> list:
    return sorted(k._stat_func.name for k in klasses)


def _pp_names(klasses) -> list:
    return sorted(k.post_processing_method for k in klasses)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_unmarked_stat_is_xorq_only(tmp_path: Path):
    """No marker means xorq: the file loads under engine="xorq" (and under
    the default, for existing callers) and not under engine="polars"."""
    _write(tmp_path, "stats", "n_rows.py", XORQ_STAT)
    assert _stat_names(load_project_stat_klasses(tmp_path)) == ["n_rows"]
    assert _stat_names(load_project_stat_klasses(tmp_path, engine="xorq")) == ["n_rows"]
    assert load_project_stat_klasses(tmp_path, engine="polars") == []


def test_polars_marked_stat_is_polars_only(tmp_path: Path):
    _write(tmp_path, "stats", "n_rows.py", POLARS_STAT)
    assert load_project_stat_klasses(tmp_path, engine="xorq") == []
    assert _stat_names(load_project_stat_klasses(tmp_path, engine="polars")) == ["n_rows"]


def test_mixed_stats_dir_splits_by_marker(tmp_path: Path):
    _write(tmp_path, "stats", "ibis_count.py", XORQ_STAT)
    _write(tmp_path, "stats", "series_len.py", POLARS_STAT)
    assert _stat_names(load_project_stat_klasses(tmp_path, engine="xorq")) == ["ibis_count"]
    assert _stat_names(load_project_stat_klasses(tmp_path, engine="polars")) == ["series_len"]


def test_stat_wrapper_marker_follows_engine(tmp_path: Path):
    """The xorq pipeline hands a stat ``table[col]`` when its parameter is
    ``XorqColumn``; the polars pipeline hands it the series when the
    parameter is ``RawSeries``. The loader has to pick the marker for the
    engine it loaded for."""
    _write(tmp_path, "stats", "ibis_count.py", XORQ_STAT)
    _write(tmp_path, "stats", "series_len.py", POLARS_STAT)
    (xorq_stat,) = load_project_stat_klasses(tmp_path, engine="xorq")
    (polars_stat,) = load_project_stat_klasses(tmp_path, engine="polars")
    assert xorq_stat._stat_func.requires[0].type is XorqColumn
    assert polars_stat._stat_func.requires[0].type is RawSeries
    assert polars_stat._stat_func.needs_raw


def test_polars_stat_runs_in_the_polars_stats_pipeline(tmp_path: Path):
    """End to end through ``PlDfStatsV2``: the loaded stat is called with
    the column's ``pl.Series`` and its value lands in the summary dict
    under the filename stem."""
    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
    from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2

    _write(tmp_path, "stats", "n_rows.py", POLARS_STAT)
    klasses = load_project_stat_klasses(tmp_path, engine="polars")
    df = pl.DataFrame({"name": ["x", "y", "z"], "age": [1, 2, 3]})
    stats = PlDfStatsV2(df, list(PL_ANALYSIS_V2) + klasses)
    assert stats.errs == {}
    assert stats.sdf["name"]["n_rows"] == 3
    assert stats.sdf["age"]["n_rows"] == 3


def test_polars_stat_sees_polars_module(tmp_path: Path):
    """A polars stat gets ``pl`` in its namespace, the way a xorq stat gets
    ``ibis`` and ``xorq``: dtype checks and expressions need it."""
    _write(tmp_path, "stats", "is_int.py",
        "ENGINE = 'polars'\n"
        "def compute(ser):\n"
        "    return ser.dtype == pl.Int64\n")
    (klass,) = load_project_stat_klasses(tmp_path, engine="polars")
    assert klass(pl.Series("a", [1, 2])) is True
    assert klass(pl.Series("a", ["x"])) is False


def test_polars_stat_can_use_module_level_constant(tmp_path: Path):
    """Same single-namespace exec the xorq loader relies on: a module-level
    constant must be visible to ``compute`` at call time."""
    _write(tmp_path, "stats", "above_threshold.py",
        "ENGINE = 'polars'\n"
        "THRESHOLD = 2\n"
        "def compute(ser):\n"
        "    return int((ser > THRESHOLD).sum())\n")
    (klass,) = load_project_stat_klasses(tmp_path, engine="polars")
    assert klass(pl.Series("a", [1, 2, 3, 4])) == 2


def test_stat_with_unknown_engine_is_skipped_by_both_loaders(tmp_path: Path):
    """A marker neither loader understands is a skipped file, not a xorq
    file by default: silently running a duckdb stat through the xorq
    pipeline would fail every column."""
    _write(tmp_path, "stats", "n_rows.py",
        "ENGINE = 'duckdb'\ndef compute(col):\n    return col.count()\n")
    assert load_project_stat_klasses(tmp_path, engine="xorq") == []
    assert load_project_stat_klasses(tmp_path, engine="polars") == []


def test_stat_loader_rejects_unknown_engine_argument(tmp_path: Path):
    _write(tmp_path, "stats", "n_rows.py", XORQ_STAT)
    with pytest.raises(ValueError):
        load_project_stat_klasses(tmp_path, engine="pandas")


# ---------------------------------------------------------------------------
# post-processing
# ---------------------------------------------------------------------------


def test_unmarked_post_processor_is_xorq_only(tmp_path: Path):
    _write(tmp_path, "post_processing", "head_two.py", XORQ_PP)
    assert _pp_names(load_project_post_processing_klasses(tmp_path)) == ["head_two"]
    assert _pp_names(load_project_post_processing_klasses(tmp_path, engine="xorq")) == ["head_two"]
    assert load_project_post_processing_klasses(tmp_path, engine="polars") == []


def test_polars_marked_post_processor_is_polars_only(tmp_path: Path):
    _write(tmp_path, "post_processing", "head_two.py", POLARS_PP)
    assert load_project_post_processing_klasses(tmp_path, engine="xorq") == []
    assert _pp_names(load_project_post_processing_klasses(tmp_path, engine="polars")) == ["head_two"]


def test_polars_post_processor_takes_and_returns_a_polars_frame(tmp_path: Path):
    """``post_process_df`` returns ``[process(df), {}]``, the shape
    ``CustomizableDataflow._compute_processed_result`` unpacks."""
    _write(tmp_path, "post_processing", "head_two.py", POLARS_PP)
    (klass,) = load_project_post_processing_klasses(tmp_path, engine="polars")
    df = pl.DataFrame({"a": [1, 2, 3]})
    out_df, sd = klass.post_process_df(df)
    assert isinstance(out_df, pl.DataFrame)
    assert out_df.height == 2
    assert sd == {}


def test_polars_post_processor_sees_polars_module(tmp_path: Path):
    _write(tmp_path, "post_processing", "with_double.py",
        "ENGINE = 'polars'\n"
        "def process(df):\n"
        "    return df.with_columns(pl.col('a') * 2)\n")
    (klass,) = load_project_post_processing_klasses(tmp_path, engine="polars")
    out_df, _sd = klass.post_process_df(pl.DataFrame({"a": [1, 2]}))
    assert out_df["a"].to_list() == [2, 4]


# ---------------------------------------------------------------------------
# import isolation
# ---------------------------------------------------------------------------


def test_project_loading_imports_without_xorq():
    """The polars ``/load`` path imports the loaders; that must not pull
    xorq into a ``buckaroo[polars]`` install. Same meta-path blocker as
    ``test_xorq_polars_isolation``."""
    script = textwrap.dedent(
        """
        import sys
        import importlib.abc

        BLOCKED = ("xorq", "buckaroo.xorq_buckaroo", "buckaroo.server.xorq_loading")

        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name in BLOCKED or any(name.startswith(b + '.') for b in BLOCKED):
                    raise ImportError(f'BLOCKED: {name}')

        sys.meta_path.insert(0, Blocker())
        import buckaroo.server.project_loading
        """)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (
        f"buckaroo.server.project_loading imported a blocked package:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")
