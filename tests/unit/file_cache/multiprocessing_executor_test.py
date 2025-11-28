import polars as pl

from buckaroo.file_cache.base import FileCache, ProgressNotification
from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor
from .executor_test_utils import SimpleColumnExecutor, SlowColumnExecutor


def test_multiprocessing_executor_success():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10,20,30]})
    ldf = df.lazy()
    fc = FileCache()
    notes: list[ProgressNotification] = []
    def listener(p: ProgressNotification):
        notes.append(p)
    exc = MultiprocessingExecutor(ldf, SimpleColumnExecutor(), listener, fc, timeout_secs=2.0)
    exc.run()
    # one notification per column
    assert len(notes) == len(df.columns)
    assert all(n.success for n in notes)
    # cache populated for each col (cannot assert exact keys)
    assert len(fc.summary_stats_cache.keys()) >= len(df.columns)


def test_multiprocessing_executor_timeout():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10,20,30]})
    ldf = df.lazy()
    fc = FileCache()
    notes: list[ProgressNotification] = []
    def listener(p: ProgressNotification):
        notes.append(p)

    # Make each column execute longer than the timeout
    exc = MultiprocessingExecutor(ldf, SlowColumnExecutor(2.5), listener, fc, timeout_secs=2.0)
    exc.run()
    # Expect two failures (one per column group) with timeout messages
    assert len(notes) == len(df.columns)
    assert all((not n.success) for n in notes)
    assert all("timeout" in (n.failure_message or "").lower() for n in notes)


