import polars as pl
from polars import functions as F

from buckaroo.file_cache.base import Executor, FileCache, ProgressNotification
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.pluggable_analysis_framework.utils import json_postfix


class SelectOnlyAnalysis(PolarsAnalysis):
    provides_defaults = {'null_count':0}
    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
    ]


def test_paf_column_executor_basic():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10, None, 30]})
    ldf = df.lazy()
    fc = FileCache()
    collected: list[ProgressNotification] = []
    def listener(p:ProgressNotification) -> None:
        collected.append(p)

    exec_ = PAFColumnExecutor([SelectOnlyAnalysis])
    ex = Executor(ldf, exec_, listener, fc)
    ex.run()

    # Should have produced two notifications and cached per-series results
    assert len(collected) == 2

    # Validate we got notifications per column (success or failure)
    assert all(p.col_group in [['a1'], ['b2']] for p in collected)


class ComputedOnlyAnalysis(PolarsAnalysis):
    """
    Minimal analysis that only provides a default and a computed_summary
    value, with no select_clauses or column_ops. This is used to verify
    that PAFColumnExecutor (via polars_series_stats_from_select_result)
    actually invokes computed_summary for each column.
    """

    provides_defaults = {'foo': 0}
    select_clauses: list[pl.Expr] = []

    @staticmethod
    def computed_summary(summary_dict):
        # Increment foo to a non-default value so we can assert it was called.
        return {'foo': summary_dict.get('foo', 0) + 1}


def test_paf_column_executor_runs_computed_summary():
    """
    Ensure that PAFColumnExecutor results include values produced by
    computed_summary, not just raw select_clauses/column_ops output.
    """
    df = pl.DataFrame({'a1': [1, 2, 3], 'b2': [10, 20, 30]})
    ldf = df.lazy()
    fc = FileCache()
    collected: list[ProgressNotification] = []

    def listener(p: ProgressNotification) -> None:
        collected.append(p)

    exec_ = PAFColumnExecutor([ComputedOnlyAnalysis])
    ex = Executor(ldf, exec_, listener, fc)
    ex.run()

    # One notification per column, and each should contain ColumnResults
    assert len(collected) == 2
    for note in collected:
        assert note.success
        assert isinstance(note.result, dict)
        # Each ColumnResult.result should contain foo==1 (default 0 + 1)
        for col, col_result in note.result.items():
            assert col in ('a1', 'b2')
            assert col_result.result.get('foo') == 1


