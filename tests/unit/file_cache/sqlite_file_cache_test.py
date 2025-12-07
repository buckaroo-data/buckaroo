import os
import socket
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import polars as pl

from buckaroo.file_cache.sqlite_file_cache import SQLiteFileCache
from buckaroo.file_cache.base import Executor, ProgressNotification
from buckaroo.file_cache.batch_planning import simple_one_column_planning
from tests.unit.file_cache.bisector_test import SimpleColumnExecutor

IS_RUNNING_LOCAL = "Paddy" in socket.gethostname()


def create_tempfile_with_text(text: str) -> Path:
    with NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt") as f:
        f.write(text)
        f.flush()
        return Path(f.name)


def test_sqlite_filecache_metadata_and_upsert():
    #FIXME
    # if not IS_RUNNING_LOCAL:
    #     #I'm having trouble wit this test in CI, and I can't tell why
    #     assert 1 == 1
    #     return
    fc = SQLiteFileCache(":memory:")
    path_1 = create_tempfile_with_text("hello")
    assert not fc.check_file(path_1)
    md = {'alpha': 1}
    fc.add_metadata(path_1, md)
    assert fc.check_file(path_1)
    assert fc.get_file_metadata(path_1) == md
    fc.upsert_file_metadata(path_1, {'beta': 2})
    assert fc.get_file_metadata(path_1) == {'alpha':1, 'beta':2}

    # change file contents -> mtime increases -> cache invalid
    path_1.write_text("world")
    # Explicitly set mtime to a future time to ensure it's different
    # (filesystem timing can be imprecise in CI, especially on low-precision filesystems)
    cached_mtime = float(fc._conn.execute("SELECT mtime FROM files WHERE path=?", (str(path_1),)).fetchone()[0])
    future_mtime = max(time.time() + 1.0, cached_mtime + 1.0)
    os.utime(path_1, (future_mtime, future_mtime))
    current_mtime = path_1.stat().st_mtime
    assert current_mtime > cached_mtime, f"mtime should increase: {current_mtime} > {cached_mtime}"
    assert not fc.check_file(path_1)


def test_sqlite_filecache_upsert_should_refresh_mtime():
    """
    Test that upsert_file_metadata refreshes mtime to the current file mtime.
    
    When a file is modified between add_metadata and upsert_file_metadata,
    upsert_file_metadata should update the cached mtime to match the current file mtime.
    """
    fc = SQLiteFileCache(":memory:")
    path_1 = create_tempfile_with_text("hello")
    
    # Step 1: Add metadata - stores mtime T1
    fc.add_metadata(path_1, {'alpha': 1})
    assert fc.check_file(path_1)
    
    # Get the mtime that was stored (T1)
    cur = fc._conn.execute("SELECT mtime FROM files WHERE path=?", (str(path_1),))
    row = cur.fetchone()
    mtime_after_add = float(row[0])
    
    # Step 2: Modify the file - mtime becomes T2 (T2 > T1)
    path_1.write_text("world")
    # Explicitly set mtime to a future time to ensure it's different
    # (filesystem timing can be imprecise in CI, especially on low-precision filesystems)
    future_mtime = max(time.time() + 1.0, mtime_after_add + 1.0)
    os.utime(path_1, (future_mtime, future_mtime))
    mtime_after_modify = path_1.stat().st_mtime
    assert mtime_after_modify > mtime_after_add, (
        f"File modification should increase mtime: {mtime_after_modify} > {mtime_after_add}"
    )
    
    # Step 3: Upsert metadata - should refresh mtime to T2
    fc.upsert_file_metadata(path_1, {'beta': 2})
    
    # Step 4: Verify the cached mtime was refreshed to current mtime (T2)
    cur = fc._conn.execute("SELECT mtime FROM files WHERE path=?", (str(path_1),))
    row = cur.fetchone()
    cached_mtime_after_upsert = float(row[0])
    
    # The cached mtime should be the current file mtime (T2), not the old one (T1)
    assert cached_mtime_after_upsert == mtime_after_modify, (
        f"upsert_file_metadata should refresh mtime to current file mtime. "
        f"Expected {mtime_after_modify}, got {cached_mtime_after_upsert}. "
        f"Original mtime was {mtime_after_add}"
    )


def test_sqlite_filecache_executor_integration():
    # Run executor and verify series results persisted in sqlite
    df = pl.DataFrame({'a1': [10,20,30], 'b2': [1,2,3]})
    ldf = df.lazy()
    fc = SQLiteFileCache(":memory:")
    collected: list[ProgressNotification] = []
    def listener(p:ProgressNotification) -> None:
        collected.append(p)

    ex = Executor(ldf, SimpleColumnExecutor(), listener, fc, planning_function=simple_one_column_planning)
    ex.run()
    # compute expected series hashes/results to cross-check what was stored
    exec_ = SimpleColumnExecutor()
    args = exec_.get_execution_args({'a1': {}, 'b2': {}})  # type: ignore
    results = exec_.execute(ldf, args)
    for col, col_res in results.items():
        stored = fc.get_series_results(col_res.series_hash)
        assert stored is not None
        assert stored.get('len') == 3

