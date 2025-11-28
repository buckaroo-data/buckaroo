from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

import polars as pl
from io import BytesIO

from .base import SummaryStats


class SQLiteFileCache:
    """
    SQLite-backed implementation of a simple file/series cache.

    Stored data:
    - files(path TEXT PRIMARY KEY, mtime REAL, metadata_json TEXT)
    - series_results(series_hash INTEGER PRIMARY KEY, result_json TEXT)
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
              path TEXT PRIMARY KEY,
              mtime REAL NOT NULL,
              metadata_json TEXT NOT NULL
            )
            """
        )
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
        self._conn.execute(
            "REPLACE INTO files(path, mtime, metadata_json) VALUES (?,?,?)",
            (str(path), mtime, json.dumps(metadata))
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
        cur = self._conn.execute("SELECT metadata_json FROM files WHERE path=?", (str(path),))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def upsert_file_metadata(self, path:Path, extra_metadata:dict[str, Any]) -> None:
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            return
        cur = self._conn.execute("SELECT mtime, metadata_json FROM files WHERE path=?", (str(path),))
        row = cur.fetchone()
        if row:
            md = json.loads(row[1])
            md.update(extra_metadata)
            # Update both metadata and mtime to reflect current file state
            self._conn.execute(
                "UPDATE files SET mtime=?, metadata_json=? WHERE path=?",
                (current_mtime, json.dumps(md), str(path))
            )
        else:
            self._conn.execute(
                "INSERT INTO files(path, mtime, metadata_json) VALUES (?,?,?)",
                (str(path), current_mtime, json.dumps(extra_metadata))
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

    # Helpers ---------------------------------------------------------------
    def _dict_to_parquet_bytes(self, d: dict[str, Any]) -> bytes:
        # Create a single-row DataFrame with dynamic columns
        df = pl.DataFrame([d])
        buf = BytesIO()
        df.write_parquet(buf)
        return buf.getvalue()

    def _parquet_bytes_to_dict(self, b: bytes) -> dict[str, Any]:
        buf = BytesIO(b)
        df = pl.read_parquet(buf)
        if df.height == 0:
            return {}
        return df.to_dicts()[0]


