"""
Global cache instances and cache management utilities.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import time

from .sqlite_file_cache import SQLiteFileCache
from .sqlite_log import SQLiteExecutorLog


# Global cache instances (initialized lazily)
_file_cache: Optional[SQLiteFileCache] = None
_executor_log: Optional[SQLiteExecutorLog] = None


def _ensure_buckaroo_dir() -> Path:
    """Ensure ~/.buckaroo directory exists."""
    buckaroo_dir = Path.home() / ".buckaroo"
    buckaroo_dir.mkdir(parents=True, exist_ok=True)
    return buckaroo_dir


def ensure_executor_sqlite() -> tuple[SQLiteFileCache, SQLiteExecutorLog]:
    """
    Ensure ~/.buckaroo directory exists and both SQLite files are initialized.
    
    Returns:
        Tuple of (file_cache, executor_log) instances
    """
    buckaroo_dir = _ensure_buckaroo_dir()
    
    file_cache_path = buckaroo_dir / "file_cache.sqlite"
    executor_log_path = buckaroo_dir / "executor_log.sqlite"
    
    # Initialize file cache with schema
    file_cache = SQLiteFileCache(str(file_cache_path))
    
    # Initialize executor log with schema
    executor_log = SQLiteExecutorLog(str(executor_log_path))
    
    return file_cache, executor_log


def get_global_file_cache() -> SQLiteFileCache:
    """Get or create the global file cache instance."""
    global _file_cache
    if _file_cache is None:
        buckaroo_dir = _ensure_buckaroo_dir()
        file_cache_path = buckaroo_dir / "file_cache.sqlite"
        _file_cache = SQLiteFileCache(str(file_cache_path))
    return _file_cache


def get_global_executor_log() -> SQLiteExecutorLog:
    """Get or create the global executor log instance."""
    global _executor_log
    if _executor_log is None:
        buckaroo_dir = _ensure_buckaroo_dir()
        executor_log_path = buckaroo_dir / "executor_log.sqlite"
        _executor_log = SQLiteExecutorLog(str(executor_log_path))
    return _executor_log


def get_cache_size() -> dict[str, int]:
    """
    Get the size in bytes of the cache files on disk.
    
    Returns:
        Dictionary with keys 'file_cache' and 'executor_log' and their sizes in bytes
    """
    buckaroo_dir = _ensure_buckaroo_dir()
    file_cache_path = buckaroo_dir / "file_cache.sqlite"
    executor_log_path = buckaroo_dir / "executor_log.sqlite"
    
    file_cache_size = file_cache_path.stat().st_size if file_cache_path.exists() else 0
    executor_log_size = executor_log_path.stat().st_size if executor_log_path.exists() else 0
    
    return {
        'file_cache': file_cache_size,
        'executor_log': executor_log_size,
        'total': file_cache_size + executor_log_size,
    }


def clear_file_cache() -> None:
    """Clear all entries from the file cache."""
    fc = get_global_file_cache()
    # Clear files table
    fc._conn.execute("DELETE FROM files")
    # Clear series_results table
    fc._conn.execute("DELETE FROM series_results")
    fc._conn.commit()


def clear_executor_log() -> None:
    """Clear all entries from the executor log."""
    log = get_global_executor_log()
    log._conn.execute("DELETE FROM events")
    log._conn.commit()


def clear_oldest_cache_entries(max_age_days: int = 30) -> int:
    """
    Clear cache entries older than the specified number of days.
    
    Args:
        max_age_days: Maximum age in days for cache entries to keep
        
    Returns:
        Number of entries deleted
    """
    fc = get_global_file_cache()
    cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
    
    # Delete old files based on mtime
    cursor = fc._conn.execute(
        "DELETE FROM files WHERE mtime < ?",
        (cutoff_time,)
    )
    files_deleted = cursor.rowcount
    
    fc._conn.commit()
    
    return files_deleted


def format_cache_size(size_bytes: int) -> str:
    """
    Format cache size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
