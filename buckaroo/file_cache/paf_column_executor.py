from __future__ import annotations

from typing import Any, List, Type

import polars as pl

from buckaroo.file_cache.base import ColumnExecutor, ColumnResults, ColumnResult, ExecutorArgs
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysis, polars_produce_series_df,
)


class PAFColumnExecutor(ColumnExecutor[ExecutorArgs]):
    """
    ColumnExecutor that delegates per-column analysis to the Polars pluggable
    analysis framework. It executes provided PolarsAnalysis classes to derive
    summary stats per column, and returns ColumnResults suitable for caching.
    """

    def __init__(self, analyses: List[Type[PolarsAnalysis]]) -> None:
        self.analyses = list(analyses)

    def get_execution_args(self, existing_stats:dict[str,dict[str,object]]) -> ExecutorArgs:
        columns = list(existing_stats.keys())
        return ExecutorArgs(
            columns=columns,
            column_specific_expressions=False,
            include_hash=True,
            expressions=[],
            row_start=None,
            row_end=None,
            extra=None,
        )

    def execute(self, ldf:pl.LazyFrame, execution_args:ExecutorArgs) -> ColumnResults:
        cols = execution_args.columns
        df = ldf.select(cols).collect()
        series_stats, errs = polars_produce_series_df(df, self.analyses, 'paf_exec', debug=False)
        return self._series_stats_to_results(df, cols, series_stats)

    def _series_stats_to_results(self,
                                 df: pl.DataFrame,
                                 cols: list[str],
                                 series_stats: dict[str, dict[str, Any]]) -> ColumnResults:
        # Compute hashes for requested columns
        hash_exprs = [pl.col(c).pl_series_hash.hash_xx().alias(c+"_hash") for c in cols]
        hashes_df = df.select(hash_exprs).collect()

        # Map rewritten entries back to original columns
        orig_to_stats: dict[str, dict[str, Any]] = {}
        for _rw, stat in series_stats.items():
            if isinstance(stat, dict):
                orig = stat.get('orig_col_name')
                if isinstance(orig, str) and orig in cols:
                    stat_copy = dict(stat)
                    stat_copy.pop('orig_col_name', None)
                    stat_copy.pop('rewritten_col_name', None)
                    orig_to_stats[orig] = stat_copy

        results: ColumnResults = {}
        for c in cols:
            hash_val = int(hashes_df[c+"_hash"][0])
            per_col_stats = orig_to_stats.get(c, {})
            results[c] = ColumnResult(
                series_hash=hash_val,
                column_name=c,
                expressions=[],
                result=per_col_stats,
            )
        return results

