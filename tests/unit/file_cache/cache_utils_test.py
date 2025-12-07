"""
Tests for cache management utilities.
"""
# state:READONLY

from pathlib import Path
import tempfile
import polars as pl

from buckaroo.file_cache.cache_utils import (
    ensure_executor_sqlite,
    get_global_file_cache,
    get_global_executor_log,
    get_cache_size,
    clear_file_cache,
    clear_executor_log,
    clear_oldest_cache_entries,
    format_cache_size,
)


def test_ensure_executor_sqlite():
    """Test that ensure_executor_sqlite creates directories and files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            file_cache, executor_log = ensure_executor_sqlite()
            
            # Check that files exist
            buckaroo_dir = Path(tmpdir) / ".buckaroo"
            assert buckaroo_dir.exists()
            assert (buckaroo_dir / "file_cache.sqlite").exists()
            assert (buckaroo_dir / "executor_log.sqlite").exists()
            
            # Check that instances are created
            assert file_cache is not None
            assert executor_log is not None
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_get_global_file_cache():
    """Test getting global file cache instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            fc = get_global_file_cache()
            assert fc is not None
            
            # Second call should return same instance (or at least work)
            fc2 = get_global_file_cache()
            assert fc2 is not None
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_get_global_executor_log():
    """Test getting global executor log instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            log = get_global_executor_log()
            assert log is not None
            
            # Second call should return same instance (or at least work)
            log2 = get_global_executor_log()
            assert log2 is not None
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_get_cache_size(tmp_path):
    """Test getting cache size."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            # Initialize caches
            ensure_executor_sqlite()
            
            sizes = get_cache_size()
            assert 'file_cache' in sizes
            assert 'executor_log' in sizes
            assert 'total' in sizes
            assert sizes['total'] == sizes['file_cache'] + sizes['executor_log']
            assert sizes['file_cache'] >= 0
            assert sizes['executor_log'] >= 0
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_clear_file_cache(tmp_path):
    """Test clearing file cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            fc = get_global_file_cache()
            test_file = Path(tmpdir) / "test.csv"
            test_df = pl.DataFrame({'a': [1, 2, 3]})
            test_df.write_csv(test_file)
            
            # Add file to cache
            fc.add_file(test_file, {'test': 'metadata'})
            
            # Verify it's in cache
            md = fc.get_file_metadata(test_file)
            assert md is not None
            assert md['test'] == 'metadata'
            
            # Clear cache
            clear_file_cache()
            
            # Verify it's gone
            md = fc.get_file_metadata(test_file)
            assert md is None
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_clear_executor_log(tmp_path):
    """Test clearing executor log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            log = get_global_executor_log()
            
            # Log should be empty initially
            events = log.get_log_events()
            
            # Clear log (should not error even if empty)
            clear_executor_log()
            
            # Log should still be empty
            events = log.get_log_events()
            assert len(events) == 0
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_clear_oldest_cache_entries(tmp_path):
    """Test clearing oldest cache entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        # Reset global instances
        import buckaroo.file_cache.cache_utils as cache_utils_module
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = tmpdir
        
        try:
            fc = get_global_file_cache()
            
            # Create test files
            file1 = Path(tmpdir) / "file1.csv"
            file2 = Path(tmpdir) / "file2.csv"
            pl.DataFrame({'a': [1]}).write_csv(file1)
            pl.DataFrame({'a': [2]}).write_csv(file2)
            
            # Add files to cache with different times
            fc.add_file(file1, {'test': 'old'})
            
            # Manually set old mtime for file1
            import time
            old_time = time.time() - (60 * 60 * 24 * 31)  # 31 days ago
            fc._conn.execute(
                "UPDATE files SET mtime = ? WHERE path = ?",
                (old_time, str(file1))
            )
            fc._conn.commit()
            
            # Add newer file
            fc.add_file(file2, {'test': 'new'})
            
            # Clear entries older than 30 days
            deleted = clear_oldest_cache_entries(max_age_days=30)
            
            # Should have deleted at least file1
            assert deleted >= 1
            
            # file1 should be gone
            md = fc.get_file_metadata(file1)
            assert md is None
            
            # file2 should still be there
            md = fc.get_file_metadata(file2)
            assert md is not None
        finally:
            # Reset global instances
            cache_utils_module._file_cache = None
            cache_utils_module._executor_log = None
            if original_home:
                os.environ['HOME'] = original_home


def test_format_cache_size():
    """Test formatting cache size."""
    assert format_cache_size(0) == "0.00 B"
    assert format_cache_size(1024) == "1.00 KB"
    assert format_cache_size(1024 * 1024) == "1.00 MB"
    assert format_cache_size(1024 * 1024 * 1024) == "1.00 GB"
    assert "B" in format_cache_size(500)
    assert "KB" in format_cache_size(2048)
