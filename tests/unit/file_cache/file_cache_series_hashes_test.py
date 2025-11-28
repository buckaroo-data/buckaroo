import os
from pathlib import Path
import tempfile

from buckaroo.file_cache.base import MemoryFileCache
from buckaroo.file_cache.sqlite_file_cache import SQLiteFileCache


def test_memory_file_cache_series_hashes_roundtrip():
    fc = MemoryFileCache()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "f.csv"
        p.write_text("a,b\n1,2\n")
        # Add base metadata and then upsert series hashes
        fc.add_file(p, {"schema": ["a", "b"]})
        fc.upsert_file_series_hashes(p, {"a": 111, "b": 222})
        hashes = fc.get_file_series_hashes(p)
        assert hashes == {"a": 111, "b": 222}
        # Merge behavior
        fc.upsert_file_series_hashes(p, {"b": 333, "c": 444})
        hashes2 = fc.get_file_series_hashes(p)
        assert hashes2 == {"a": 111, "b": 333, "c": 444}
        # Other metadata preserved
        md = fc.get_file_metadata(p)
        assert md and md.get("schema") == ["a", "b"]


def test_sqlite_file_cache_series_hashes_roundtrip(tmp_path):
    db_path = tmp_path / "cache.db"
    fc = SQLiteFileCache(str(db_path))
    p = tmp_path / "f.parquet"
    p.write_text("x")  # just to have a file; mtime exists
    fc.add_file(p, {"schema": ["c1", "c2"]})
    fc.upsert_file_series_hashes(p, {"c1": 999})
    hashes = fc.get_file_series_hashes(p)
    assert hashes == {"c1": 999}
    # Merge
    fc.upsert_file_series_hashes(p, {"c2": 123})
    assert fc.get_file_series_hashes(p) == {"c1": 999, "c2": 123}
    # Metadata preserved
    md = fc.get_file_metadata(p)
    assert md and md.get("schema") == ["c1", "c2"]

