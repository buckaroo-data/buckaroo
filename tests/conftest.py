import pytest


@pytest.fixture(autouse=True)
def isolate_caches(monkeypatch):
    """Give each test its own in-memory SQLite instances.

    Prevents xdist workers from contending on ~/.buckaroo/*.sqlite files,
    which causes 'database is locked' failures under parallel load.
    """
    import buckaroo.file_cache.cache_utils as cache_utils
    from buckaroo.file_cache.sqlite_log import SQLiteExecutorLog
    from buckaroo.file_cache.sqlite_file_cache import SQLiteFileCache

    monkeypatch.setattr(cache_utils, "_executor_log", SQLiteExecutorLog(":memory:"))
    monkeypatch.setattr(cache_utils, "_file_cache", SQLiteFileCache(":memory:"))
