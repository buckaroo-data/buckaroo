from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from io import BytesIO

from .base import SummaryStats, AbstractFileCache


class SQLiteFileCache(AbstractFileCache):
    """
    SQLite-backed implementation of a simple file/series cache.

    Stored data:
    - files(path TEXT PRIMARY KEY, mtime REAL, metadata_json TEXT)
    - series_results(series_hash INTEGER PRIMARY KEY, result_json TEXT)
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
              path TEXT PRIMARY KEY,
              mtime REAL NOT NULL,
              metadata_json TEXT NOT NULL
            )
            """
        )
        # Add merged_sd_blob column if it doesn't exist (schema migration)
        try:
            self._conn.execute("ALTER TABLE files ADD COLUMN merged_sd_blob BLOB")
            self._conn.commit()
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series_results (
              series_hash TEXT PRIMARY KEY,
              result_blob BLOB NOT NULL
            )
            """
        )
        self._conn.commit()

    # File metadata API -----------------------------------------------------
    def add_file(self, path:Path, metadata:dict[str, Any]) -> None:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return
        # Extract merged_sd if present
        merged_sd_blob = None
        metadata_without_merged_sd = {}
        for k, v in metadata.items():
            if k == 'merged_sd' and isinstance(v, dict) and len(v) > 0:
                merged_sd_blob = self._merged_sd_to_parquet_blob(v)
            else:
                try:
                    json.dumps(v)  # Test if serializable
                    metadata_without_merged_sd[k] = v
                except (TypeError, ValueError):
                    metadata_without_merged_sd[k] = str(v)
        self._conn.execute(
            "REPLACE INTO files(path, mtime, metadata_json, merged_sd_blob) VALUES (?,?,?,?)",
            (str(path), mtime, json.dumps(metadata_without_merged_sd), merged_sd_blob)
        )
        self._conn.commit()

    def add_metadata(self, path:Path, metadata:dict[str, Any]) -> None:
        self.add_file(path, metadata)

    def check_file(self, path:Path) -> bool:
        cur = self._conn.execute("SELECT mtime FROM files WHERE path=?", (str(path),))
        row = cur.fetchone()
        if not row:
            return False
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            return False
        cached_mtime = float(row[0])
        return current_mtime <= cached_mtime

    def get_file_metadata(self, path:Path) -> Optional[dict[str, Any]]:
        # Check if merged_sd_blob column exists
        try:
            cur = self._conn.execute("SELECT metadata_json, merged_sd_blob FROM files WHERE path=?", (str(path),))
        except sqlite3.OperationalError:
            # Column doesn't exist yet, use old schema
            cur = self._conn.execute("SELECT metadata_json FROM files WHERE path=?", (str(path),))
            row = cur.fetchone()
            if not row:
                return None
            return json.loads(row[0])
        
        row = cur.fetchone()
        if not row:
            return None
        md = json.loads(row[0])
        # Load merged_sd from parquet blob if present
        merged_sd_blob = row[1] if len(row) > 1 else None
        if merged_sd_blob:
            try:
                merged_sd = self._parquet_blob_to_merged_sd(merged_sd_blob)
                if merged_sd:
                    md['merged_sd'] = merged_sd
            except Exception:
                # If deserialization fails, continue without merged_sd
                pass
        return md

    def _merged_sd_to_parquet_blob(self, merged_sd: dict[str, dict[str, Any]]) -> bytes:
        """Convert merged_sd dict to parquet blob for storage."""
        import polars as pl
        # Store as parquet with one row per (column, stat_key) pair
        # Store all values as JSON strings to avoid schema inference issues with mixed types
        rows = []
        for col_name, col_stats in merged_sd.items():
            if not isinstance(col_stats, dict):
                continue
            
            for stat_key, stat_val in col_stats.items():
                # Convert stat value to JSON string for consistent storage
                try:
                    # Try to JSON serialize the value
                    val_json = json.dumps(stat_val, default=str)  # default=str handles non-serializable types
                    rows.append({
                        'col_name': str(col_name),
                        'stat_key': str(stat_key),
                        'val_json': val_json
                    })
                except Exception:
                    # If JSON serialization fails, convert to string
                    rows.append({
                        'col_name': str(col_name),
                        'stat_key': str(stat_key),
                        'val_json': json.dumps(str(stat_val))
                    })
        
        if not rows:
            # Return empty parquet if no data
            df = pl.DataFrame()
        else:
            # Create DataFrame with explicit schema to avoid inference issues
            df = pl.DataFrame(rows, schema={'col_name': pl.String, 'stat_key': pl.String, 'val_json': pl.String})
        
        buf = BytesIO()
        df.write_parquet(buf)
        return buf.getvalue()
    
    def _parquet_blob_to_merged_sd(self, blob: bytes) -> Optional[dict[str, dict[str, Any]]]:
        """Convert parquet blob back to merged_sd dict."""
        import polars as pl
        if not blob:
            return None
        try:
            buf = BytesIO(blob)
            df = pl.read_parquet(buf)
            if df.height == 0:
                return {}
            
            # Reconstruct merged_sd from parquet rows
            merged_sd: dict[str, dict[str, Any]] = {}
            
            for row in df.to_dicts():
                col_name = row.get('col_name')
                stat_key = row.get('stat_key')
                val_json = row.get('val_json')
                
                if col_name and stat_key is not None and val_json is not None:
                    if col_name not in merged_sd:
                        merged_sd[col_name] = {}
                    
                    # Deserialize JSON string
                    try:
                        merged_sd[col_name][stat_key] = json.loads(val_json)
                    except Exception:
                        # If JSON parsing fails, keep as string
                        merged_sd[col_name][stat_key] = val_json
            
            return merged_sd
        except Exception:
            return None

    def upsert_file_metadata(self, path:Path, extra_metadata:dict[str, Any]) -> None:
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            return
        
        # Extract merged_sd if present - store it separately as parquet blob
        merged_sd_blob = None
        metadata_without_merged_sd = {}
        for k, v in extra_metadata.items():
            if k == 'merged_sd' and isinstance(v, dict) and len(v) > 0:
                # Store merged_sd as parquet blob
                merged_sd_blob = self._merged_sd_to_parquet_blob(v)
            else:
                # For other metadata, serialize for JSON
                try:
                    json.dumps(v)  # Test if serializable
                    metadata_without_merged_sd[k] = v
                except (TypeError, ValueError):
                    metadata_without_merged_sd[k] = str(v)
        
        cur = self._conn.execute("SELECT mtime, metadata_json FROM files WHERE path=?", (str(path),))
        row = cur.fetchone()
        if row:
            md = json.loads(row[1])
            md.update(metadata_without_merged_sd)
            # Update metadata, mtime, and merged_sd_blob
            self._conn.execute(
                "UPDATE files SET mtime=?, metadata_json=?, merged_sd_blob=? WHERE path=?",
                (current_mtime, json.dumps(md), merged_sd_blob, str(path))
            )
        else:
            self._conn.execute(
                "INSERT INTO files(path, mtime, metadata_json, merged_sd_blob) VALUES (?,?,?,?)",
                (str(path), current_mtime, json.dumps(metadata_without_merged_sd), merged_sd_blob)
            )
        self._conn.commit()

    # Series results API ----------------------------------------------------
    def upsert_key(self, series_hash:int, result:SummaryStats) -> None:
        # Merge with existing result stored as parquet blob
        cur = self._conn.execute("SELECT result_blob FROM series_results WHERE series_hash=?", (str(series_hash),))
        row = cur.fetchone()
        if row:
            existing_blob: bytes = row[0]
            current = self._parquet_bytes_to_dict(existing_blob)
            current.update(result)
        else:
            current = dict(result)
        blob = self._dict_to_parquet_bytes(current)
        self._conn.execute(
            "REPLACE INTO series_results(series_hash, result_blob) VALUES (?,?)",
            (str(series_hash), blob)
        )
        self._conn.commit()

    def get_series_results(self, series_hash:int) -> SummaryStats|None:
        cur = self._conn.execute("SELECT result_blob FROM series_results WHERE series_hash=?", (str(series_hash),))
        row = cur.fetchone()
        if not row:
            return None
        return self._parquet_bytes_to_dict(row[0])

    # New: file-level series hashes helpers
    def get_file_series_hashes(self, path: Path) -> Optional[dict[str, int]]:
        md = self.get_file_metadata(path)
        if not md:
            return None
        return md.get('series_hashes')

    def upsert_file_series_hashes(self, path: Path, hashes: dict[str, int]) -> None:
        md = self.get_file_metadata(path) or {}
        current = dict(md.get('series_hashes') or {})
        current.update({str(k): int(v) for k, v in hashes.items()})
        merged = dict(md)
        merged['series_hashes'] = current
        self.upsert_file_metadata(path, merged)

    # Helpers ---------------------------------------------------------------
    def _dict_to_parquet_bytes(self, d: dict[str, Any]) -> bytes:
        import polars as pl
        # Create a single-row DataFrame with dynamic columns
        # Convert non-serializable values to strings to avoid parquet errors
        serializable_dict = {}
        for k, v in d.items():
            if isinstance(v, (int, float, str, bool, type(None))):
                serializable_dict[k] = v
            elif isinstance(v, (list, tuple)):
                # Try to keep lists/tuples if they're serializable, otherwise convert to string
                try:
                    # Test if it can be serialized by trying to create a DataFrame
                    pl.DataFrame({k: [v]})  # Just test, don't store
                    serializable_dict[k] = v
                except Exception:
                    serializable_dict[k] = str(v)
            else:
                # For complex types (like dtype objects), convert to string
                serializable_dict[k] = str(v)
        
        df = pl.DataFrame([serializable_dict])
        buf = BytesIO()
        df.write_parquet(buf)
        return buf.getvalue()

    def _parquet_bytes_to_dict(self, b: bytes) -> dict[str, Any]:
        import polars as pl
        buf = BytesIO(b)
        df = pl.read_parquet(buf)
        if df.height == 0:
            return {}
        return df.to_dicts()[0]


