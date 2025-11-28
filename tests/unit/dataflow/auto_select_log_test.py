from datetime import datetime as dtdt
from buckaroo.file_cache.base import ExecutorArgs, ExecutorLogEvent

import polars as pl

from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
from buckaroo.file_cache.base import Executor as _Exec, SimpleExecutorLog


# Instrumentation executors for the test:
# - They flip a class-level `used` flag in run() so assertions can verify which
#   executor actually executed.
# - Their distinct class names are recorded in the executor log, enabling the
#   test to simulate "sync previously incomplete → choose parallel" behavior.
class TrackingSync(_Exec):
    used = False
    def run(self):  # type: ignore[override]
        TrackingSync.used = True
        return super().run()

class TrackingPar(_Exec):
    used = False
    def run(self):  # type: ignore[override]
        TrackingPar.used = True
        return super().run()


def test_auto_select_uses_parallel_if_sync_incomplete_logged():
    df = pl.DataFrame({'a':[1,2,3], 'b':[4,5,6]})
    ldf = df.lazy()
    log = SimpleExecutorLog()
    dfi = (id(ldf), "",)
    # fabricate an incomplete event for TrackingSync
    fake_args = ExecutorArgs(columns=['a'], column_specific_expressions=False, include_hash=True,
                             expressions=[], row_start=None, row_end=None, extra=None)
    log._events.append(ExecutorLogEvent(dfi=dfi, args=fake_args, executor_class_name=TrackingSync.__name__,
                                        start_time=dtdt.now(), end_time=None, completed=False))  # type: ignore[arg-type]

    cdf = ColumnExecutorDataflow(ldf, executor_log=log)
    cdf.auto_compute_summary(TrackingSync, TrackingPar)
    # parallel should be used due to log
    assert TrackingPar.used is True
    assert TrackingSync.used is False

