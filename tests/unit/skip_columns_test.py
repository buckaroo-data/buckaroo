"""skip_columns: stats supplied via init_sd must not be recomputed.

A column whose summary stats are provided externally (e.g. reused from a
source dataframe in a diff/comparison) should be skipped by the stat pipeline
— it still appears in the output (with structural metadata) but no stat
expressions are built/executed for it.  Same behaviour across backends.
"""
import pandas as pd
import pytest

from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.pluggable_analysis_framework.stat_units import StatState
from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2


def test_pandas_skip_columns_not_computed():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    pipe = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
    sd, errs = pipe.process_df(df, skip_columns={"b"})
    assert "a" in sd and "b" in sd            # both columns still present
    assert "mean" in sd["a"]                  # a was computed
    assert "mean" not in sd["b"]              # b was skipped
    assert set(sd["b"]) <= {"orig_col_name", "rewritten_col_name"}


def test_pandas_no_skip_is_unchanged():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    pipe = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
    sd, _ = pipe.process_df(df)
    assert "mean" in sd["a"] and "mean" in sd["b"]


def test_pandas_shim_threads_skip_columns():
    from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    stats = DfStatsV2(df, PD_ANALYSIS_V2, skip_columns={"b"})
    assert "mean" in stats.sdf["a"] and "mean" not in stats.sdf["b"]


def test_polars_shim_threads_skip_columns():
    pl = pytest.importorskip("polars")
    from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
    df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    stats = PlDfStatsV2(df, PL_ANALYSIS_V2, skip_columns={"b"})
    assert "mean" in stats.sdf["a"] and "mean" not in stats.sdf["b"]


def test_xorq_skip_columns_not_computed(tmp_path):
    xo = pytest.importorskip("xorq.api")
    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline
    from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2

    p = tmp_path / "t.parquet"
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_parquet(p)
    expr = xo.deferred_read_parquet(str(p))

    pipe = XorqStatPipeline(XORQ_STATS_V2)
    sd, errs = pipe.process_table(expr, skip_columns={"b"})
    assert "a" in sd and "b" in sd
    assert "mean" in sd["a"]
    assert "mean" not in sd["b"]


# ---------------------------------------------------------------------------
# Resumable units (rows-first s4): a skipped column gets no unit, so running
# every unit never touches it, and it still ends up in the result.
# ---------------------------------------------------------------------------


def _run_units(pipe, state):
    acc = pipe.new_accumulator(state)
    return acc, [pipe.run(unit, acc) for unit in pipe.plan(state)]


def test_pandas_skipped_column_gets_no_unit():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    pipe = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
    state = StatState(df, skip_columns=frozenset({"b"}))
    assert [u.columns for u in pipe.plan(state)] == [("a",), ("c",)]
    acc, fragments = _run_units(pipe, state)
    assert [list(f) for f in fragments] == [["a"], ["c"]]
    assert list(acc.sd()) == ["a", "b", "c"], "the skipped column keeps its place in the result"
    assert acc.sd()["b"] == {"orig_col_name": "b", "rewritten_col_name": "b"}
    assert pipe.process_df(df, skip_columns={"b"})[0]["b"] == acc.sd()["b"]


def test_polars_skipped_column_gets_no_unit():
    pl = pytest.importorskip("polars")
    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
    df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    pipe = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
    state = StatState(df, skip_columns=frozenset({"b"}))
    assert [u.columns for u in pipe.plan(state)] == [("a",), ("c",)]
    acc, _fragments = _run_units(pipe, state)
    assert set(acc.sd()["b"]) <= {"orig_col_name", "rewritten_col_name"}


def test_xorq_skipped_column_gets_no_unit(tmp_path):
    xo = pytest.importorskip("xorq.api")
    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline
    from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2

    p = tmp_path / "t.parquet"
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_parquet(p)
    expr = xo.deferred_read_parquet(str(p))

    pipe = XorqStatPipeline(XORQ_STATS_V2)
    state = StatState(expr, skip_columns=frozenset({"b"}))
    units = pipe.plan(state)
    assert all("b" not in unit.columns for unit in units)
    assert [u.id for u in units] == ["batch", "histogram:a"]
    acc, fragments = _run_units(pipe, state)
    assert all("b" not in fragment for fragment in fragments)
    sd = acc.sd()
    # The column keeps what the batch gives every column, and no stat of its own.
    assert sd["b"]["length"] == 3 and sd["b"]["dtype"] == "int64"
    assert "mean" not in sd["b"] and "histogram" not in sd["b"]
    assert sd == pipe.process_table(expr, skip_columns={"b"})[0]


# ---------------------------------------------------------------------------
# Notebook widget constructors must forward skip_stat_columns to the dataflow
# (it was only wired into CustomizableDataflow + the server /load handler, not
# the widget classes a notebook user instantiates).
# ---------------------------------------------------------------------------


def _by_orig(sd, orig_name):
    return next(v for v in sd.values() if v.get("orig_col_name") == orig_name)


def test_buckaroo_widget_threads_skip_stat_columns():
    from buckaroo import BuckarooWidget
    df = pd.DataFrame({"alpha": [1, 2, 3, 4], "beta": [10, 20, 30, 40]})
    sd = BuckarooWidget(df, skip_stat_columns=["beta"]).dataflow.merged_sd
    assert "mean" in _by_orig(sd, "alpha")      # computed
    assert "mean" not in _by_orig(sd, "beta")   # skipped


def test_buckaroo_infinite_widget_threads_skip_stat_columns():
    from buckaroo import BuckarooInfiniteWidget
    df = pd.DataFrame({"alpha": [1, 2, 3, 4], "beta": [10, 20, 30, 40]})
    sd = BuckarooInfiniteWidget(df, skip_stat_columns=["beta"]).dataflow.merged_sd
    assert "mean" in _by_orig(sd, "alpha")
    assert "mean" not in _by_orig(sd, "beta")


def test_widget_skip_preserves_supplied_init_sd():
    """The point of skipping: stats supplied via init_sd survive because the
    column is not recomputed. Without skip the computed value overrides them."""
    from buckaroo import BuckarooWidget
    df = pd.DataFrame({"alpha": [1, 2, 3, 4], "beta": [10, 20, 30, 40]})  # real beta mean = 25
    supplied = {"beta": {"mean": 999.0}}
    assert _by_orig(BuckarooWidget(df, init_sd=supplied).dataflow.merged_sd, "beta")["mean"] == 25.0
    assert _by_orig(BuckarooWidget(df, init_sd=supplied, skip_stat_columns=["beta"]).dataflow.merged_sd,
                    "beta")["mean"] == 999.0


def test_polars_widget_threads_skip_stat_columns():
    pl = pytest.importorskip("polars")
    from buckaroo.polars_buckaroo import PolarsBuckarooWidget
    pdf = pl.DataFrame({"alpha": [1, 2, 3, 4], "beta": [10, 20, 30, 40]})
    sd = PolarsBuckarooWidget(pdf, skip_stat_columns=["beta"]).dataflow.merged_sd
    assert "mean" in _by_orig(sd, "alpha")
    assert "mean" not in _by_orig(sd, "beta")
