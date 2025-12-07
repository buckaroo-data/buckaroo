import polars as pl

from buckaroo.file_cache.base import (
    FileCache,
    Executor,
    ProgressNotification,
)
from buckaroo.file_cache.batch_planning import simple_one_column_planning
from buckaroo.file_cache.sqlite_log import SQLiteExecutorLog
from tests.unit.file_cache.bisector_test import SimpleColumnExecutor, FailOnSumExecutor  # reuse helpers


def test_sqlite_executor_log_success_in_memory():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [4,5,6]})
    ldf = df.lazy()
    fc = FileCache()
    log = SQLiteExecutorLog(":memory:")
    calls = []
    def listener(p:ProgressNotification) -> None:
        calls.append(p)

    ex = Executor(ldf, SimpleColumnExecutor(), listener, fc, executor_log=log, planning_function=simple_one_column_planning)
    ex.run()

    events = log.get_log_events()
    # two column groups executed and completed
    assert len(events) == 2
    assert all(ev.completed for ev in events)
    # check columns recorded
    cols_sets = [tuple(ev.args.columns) for ev in events]
    assert ('a1',) in cols_sets and ('b2',) in cols_sets


def test_sqlite_executor_log_failure_and_previous_failure_check(tmp_path):
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [4,5,6]})
    ldf = df.lazy()
    fc = FileCache()
    db_path = tmp_path / "exec_log.db"
    log = SQLiteExecutorLog(str(db_path))

    def listener(p:ProgressNotification) -> None:
        pass

    ex = Executor(ldf, FailOnSumExecutor(), listener, fc, executor_log=log, planning_function=simple_one_column_planning)
    ex.run()

    # Persisted events
    events = log.get_log_events()
    assert len(events) == 2
    # One of them should be incomplete (failure)
    assert any(not ev.completed for ev in events)

    # Reopen the log and verify previous failure detection works
    log2 = SQLiteExecutorLog(str(db_path))
    # pick an incomplete event and ensure the API reports previous failure
    incomplete = next(ev for ev in log2.get_log_events() if not ev.completed)
    assert log2.check_log_for_previous_failure(incomplete.dfi, incomplete.args) is True


