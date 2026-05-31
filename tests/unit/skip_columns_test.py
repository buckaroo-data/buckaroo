"""skip_columns: stats supplied via init_sd must not be recomputed.

A column whose summary stats are provided externally (e.g. reused from a
source dataframe in a diff/comparison) should be skipped by the stat pipeline
— it still appears in the output (with structural metadata) but no stat
expressions are built/executed for it.  Same behaviour across backends.
"""
import pandas as pd
import pytest

from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
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
