import polars as pl
import polars.selectors as cs
import time
from typing import cast

from buckaroo.file_cache.base import (
    ColumnExecutor,
    ExecutorArgs,
    ColumnResults,
    ColumnResult,
)


class SimpleColumnExecutor(ColumnExecutor[ExecutorArgs]):
    def get_execution_args(self, existing_stats:dict[str,dict[str,object]]) -> ExecutorArgs:
        columns = list(existing_stats.keys())
        return ExecutorArgs(
            columns=columns,
            column_specific_expressions=False,
            include_hash=True,
            expressions=[
                cs.numeric().sum().name.suffix("_sum"),
                pl.len().name.suffix("_len"),
            ],
            row_start=None,
            row_end=None,
            extra=None,
        )

    def execute(self, ldf:pl.LazyFrame, execution_args:ExecutorArgs) -> ColumnResults:
        cols = execution_args.columns
        only_cols_ldf = ldf.select(cols)
        res = only_cols_ldf.select(*execution_args.expressions).collect()

        col_results: ColumnResults = {}
        for col in cols:
            # Use a deterministic series_hash for tests without relying on pl_series_hash
            hash_: int = hash(col) & ((1 << 63) - 1)
            actual_result = {"len": res[col+"_len"][0] if col+"_len" in res.columns else 0}
            if col+"_sum" in res.columns:
                actual_result["sum"] = res[col+"_sum"][0]
            cr = ColumnResult(
                series_hash=hash_,
                column_name=col,
                expressions=[],
                result=actual_result,
            )
            col_results[col] = cr
        return col_results


class SlowColumnExecutor(SimpleColumnExecutor):
    def __init__(self, delay_sec: float) -> None:
        super().__init__()
        self.delay_sec = delay_sec
    def execute(self, ldf: pl.LazyFrame, execution_args: ExecutorArgs) -> ColumnResults:
        time.sleep(self.delay_sec)
        return super().execute(ldf, execution_args)


