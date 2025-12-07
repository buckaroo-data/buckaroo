from __future__ import annotations

import sqlite3
import json
from typing import Optional
from datetime import datetime as dtdt

from .base import ExecutorLog, ExecutorLogEvent, ExecutorArgs, DFIdentifier


def _dfi_key(dfi: DFIdentifier) -> str:
    return json.dumps([str(dfi[0]), dfi[1]])


class SQLiteExecutorLog(ExecutorLog):
    """
    SQLite-backed implementation of ExecutorLog. Stores minimal, serializable
    details of ExecutorArgs sufficient to:
      - detect previous incomplete runs for the same (dfi, columns, rows, flags)
      - reconstruct ExecutorLogEvent objects for inspection
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY,
              dfi TEXT NOT NULL,
              columns_json TEXT NOT NULL,
              include_hash INTEGER NOT NULL,
              row_start INTEGER,
              row_end INTEGER,
              expr_count INTEGER,
              completed INTEGER NOT NULL,
              start_time TEXT NOT NULL,
              end_time TEXT
            )
            """
        )
        self._conn.commit()

    def _args_key_parts(self, args: ExecutorArgs) -> tuple[str, int, Optional[int], Optional[int], int]:
        cols = json.dumps(list(args.columns))
        include_hash = 1 if args.include_hash else 0
        row_start = args.row_start
        row_end = args.row_end
        expr_count = len(args.expressions)
        return cols, include_hash, row_start, row_end, expr_count

    def log_start_col_group(self, dfi: DFIdentifier, args:ExecutorArgs, executor_class_name:str = "") -> None:
        dfi_k = _dfi_key(dfi)
        cols, include_hash, row_start, row_end, expr_count = self._args_key_parts(args)
        self._conn.execute(
            "INSERT INTO events (dfi, columns_json, include_hash, row_start, row_end, expr_count, completed, start_time, end_time) VALUES (?,?,?,?,?,?,?,?,?)",
            (dfi_k, cols, include_hash, row_start, row_end, expr_count, 0, dtdt.now().isoformat(), None)
        )
        self._conn.commit()

    def log_end_col_group(self, dfi: DFIdentifier, args:ExecutorArgs) -> None:
        dfi_k = _dfi_key(dfi)
        cols, include_hash, row_start, row_end, expr_count = self._args_key_parts(args)
        self._conn.execute(
            """
            UPDATE events SET completed=1, end_time=?
            WHERE id = (
              SELECT id FROM events
              WHERE dfi=? AND columns_json=? AND include_hash=? AND IFNULL(row_start,-1)=IFNULL(?, -1) AND IFNULL(row_end,-1)=IFNULL(?, -1)
              ORDER BY id DESC LIMIT 1
            )
            """,
            (dtdt.now().isoformat(), dfi_k, cols, include_hash, row_start, row_end)
        )
        self._conn.commit()

    def check_log_for_previous_failure(self, dfi: DFIdentifier, args:ExecutorArgs) -> bool:
        dfi_k = _dfi_key(dfi)
        cols, include_hash, row_start, row_end, expr_count = self._args_key_parts(args)
        cur = self._conn.execute(
            """
            SELECT COUNT(1) FROM events
            WHERE dfi=? AND columns_json=? AND include_hash=? AND IFNULL(row_start,-1)=IFNULL(?, -1) AND IFNULL(row_end,-1)=IFNULL(?, -1) AND completed=0
            """,
            (dfi_k, cols, include_hash, row_start, row_end)
        )
        (cnt,) = cur.fetchone()
        return cnt > 0
    
    def check_log_for_completed(self, dfi: DFIdentifier, args:ExecutorArgs) -> bool:
        """
        Check if this column group was already completed successfully.
        Returns True if there is a completed event with matching args.
        """
        dfi_k = _dfi_key(dfi)
        cols, include_hash, row_start, row_end, expr_count = self._args_key_parts(args)
        cur = self._conn.execute(
            """
            SELECT COUNT(1) FROM events
            WHERE dfi=? AND columns_json=? AND include_hash=? AND IFNULL(row_start,-1)=IFNULL(?, -1) AND IFNULL(row_end,-1)=IFNULL(?, -1) AND completed=1
            """,
            (dfi_k, cols, include_hash, row_start, row_end)
        )
        (cnt,) = cur.fetchone()
        return cnt > 0

    def get_log_events(self) -> list[ExecutorLogEvent]:
        res: list[ExecutorLogEvent] = []
        cur = self._conn.execute("SELECT dfi, columns_json, include_hash, row_start, row_end, expr_count, completed, start_time, end_time FROM events ORDER BY id ASC")
        for row in cur.fetchall():
            dfi_k, cols_json, include_hash, row_start, row_end, expr_count, completed, start_s, end_s = row
            # Reconstruct dfi
            dfi_dec = json.loads(dfi_k)
            dfi: DFIdentifier = (dfi_dec[0], dfi_dec[1])  # type: ignore
            # Reconstruct minimal args (expressions omitted for log purposes)
            args = ExecutorArgs(
                columns=list(json.loads(cols_json)),
                column_specific_expressions=False,
                include_hash=bool(include_hash),
                expressions=[],
                row_start=row_start,
                row_end=row_end,
                extra=None,
            )
            ev = ExecutorLogEvent(
                dfi=dfi,
                args=args,
                start_time=dtdt.fromisoformat(start_s),
                end_time=dtdt.fromisoformat(end_s) if end_s else None,
                completed=bool(completed),
            )
            res.append(ev)
        return res

    def has_incomplete_for_executor(self, dfi: DFIdentifier, executor_class_name: str) -> bool:
        """
        Check if there are incomplete events for the given dataframe identifier and executor class.
        """
        dfi_k = _dfi_key(dfi)
        # Note: executor_class_name is not stored in the SQLite schema currently,
        # so we check for any incomplete events for this dfi
        cur = self._conn.execute(
            "SELECT COUNT(1) FROM events WHERE dfi=? AND completed=0",
            (dfi_k,)
        )
        (cnt,) = cur.fetchone()
        return cnt > 0


