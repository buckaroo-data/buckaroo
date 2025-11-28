import time
import polars as pl

from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor


class SlowPAFColumnExecutor(PAFColumnExecutor):
    def execute(self, ldf, execution_args):
        # simulate work per column group (no Python concurrency)
        time.sleep(0.1)
        return super().execute(ldf, execution_args)


def test_polars_only_progress_streams_sequentially():
    df = pl.DataFrame({'c1': [1, 2, 3], 'c2': [10, 20, 30], 'c3': [7, 8, 9]})
    ldf = df.lazy()

    # capture partial updates from dataflow
    partial_counts = []
    def on_progress(agg):
        partial_counts.append(len(agg.keys()))

    cdf = ColumnExecutorDataflow(
        ldf,
        column_executor_class=SlowPAFColumnExecutor
    )
    cdf.progress_update_callback = on_progress

    # run compute synchronously; updates should stream sequentially
    cdf.compute_summary_with_executor()

    # final merged_sd should have all 3 columns
    assert len(cdf.merged_sd.keys()) == 3
    # and we should have seen intermediate updates (1..3)
    assert partial_counts and partial_counts[-1] == 3

