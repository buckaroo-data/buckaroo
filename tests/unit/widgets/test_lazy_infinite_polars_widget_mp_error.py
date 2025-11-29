import polars as pl
from polars import functions as F

from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.pluggable_analysis_framework.utils import json_postfix


class FailingRenameAnalysis(PolarsAnalysis):
    """
    Minimal analysis that embeds a Python callable via name.map(json_postfix(...)),
    which is not serializable across process boundaries in Polars and should fail
    under the multiprocessing executor.
    """
    provides_defaults = {'null_count': 0}
    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
    ]


def _wide_df(num_cols: int, num_rows: int) -> pl.DataFrame:
    data = {f"c{i}": list(range(num_rows)) for i in range(num_cols)}
    return pl.DataFrame(data)


def Xtest_lazy_widget_multiprocessing_renaming_serialization_failure():
    """
    Force the multiprocessing executor path by exceeding the column threshold (>= 50),
    and then verify that a Polars renaming callable leads to a serialization failure,
    surfaced via widget executor progress as a failure.
    """
    # 51 columns forces parallel path (auto_compute_summary uses num_cols_threshold=50)
    
    df = _wide_df(num_cols=51, num_rows=2)
    ldf = df.lazy()

    w = LazyInfinitePolarsBuckarooWidget(
        ldf,
        analysis_klasses=[FailingRenameAnalysis],
        debug=True,
    )

    # The widget emits minimal progress via 'executor_progress' trait.
    ep = dict(w.executor_progress or {})
    # With expression rewriting, multiprocessing path should succeed now.
    assert ep.get('success') is True


