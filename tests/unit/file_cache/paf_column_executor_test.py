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


