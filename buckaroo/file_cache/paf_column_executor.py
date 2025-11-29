from __future__ import annotations

from typing import Any, List, Type
import json

import polars as pl

from buckaroo.file_cache.base import ColumnExecutor, ColumnResults, ColumnResult, ExecutorArgs
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysis, polars_select_expressions, polars_series_stats_from_select_result,
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
        # include hash only if any column is marked missing via sentinel
        include_hash = any(bool(stats.get('__missing_hash__')) for stats in existing_stats.values())

        # Use the EXACT same expressions as regular PAF to ensure identical results
        # This ensures PAFColumnExecutor is a drop-in replacement for regular PAF
        expressions: list[pl.Expr] = polars_select_expressions(self.analyses)

        return ExecutorArgs(
            columns=columns,
            column_specific_expressions=False,  # Using same expressions as regular PAF (not per-column)
            include_hash=include_hash,
            expressions=expressions,
            row_start=None,
            row_end=None,
            extra=None,
        )

    def execute(self, ldf:pl.LazyFrame, execution_args:ExecutorArgs) -> ColumnResults:
        cols = execution_args.columns
        only_cols = ldf.select(cols)
        
        # Try to execute all expressions together first (like polars_produce_series_df)
        try:
            res = only_cols.select(*execution_args.expressions).collect()
        except Exception:
            # Fallback: Execute expressions individually and combine horizontally
            # This matches the behavior of polars_produce_series_df (lines 46-82)
            # to handle cases where some expressions fail (e.g., mean() on string columns)
            individual_results = []
            for expr in execution_args.expressions:
                try:
                    expr_result = only_cols.select(expr).collect()
                    individual_results.append(expr_result)
                except Exception:
                    # Skip failed expression, continue with others
                    # This allows value_counts and other valid expressions to succeed
                    # even if mean() or other operations fail on string columns
                    continue
            
            # Try to combine results horizontally
            if individual_results:
                try:
                    res = individual_results[0]
                    for additional_result in individual_results[1:]:
                        res = res.hstack(additional_result)
                except Exception:
                    # If hstack fails (e.g., height mismatches), extract values from each
                    # result separately and merge them, then reconstruct a DataFrame
                    # This ensures we get all available values even when heights don't match
                    # split_to_dicts only reads the first row, so we can put all values in row 0
                    from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts
                    from collections import defaultdict
                    
                    merged_dict = defaultdict(dict)
                    for individual_result in individual_results:
                        result_dict = split_to_dicts(individual_result)
                        for orig_col, measures in result_dict.items():
                            merged_dict[orig_col].update(measures)
                    
                    # Reconstruct DataFrame from merged dict
                    # split_to_dicts only reads stat_df[col][0], so we put all values in row 0
                    # For value_counts, we need to preserve the Series structure
                    # For other measures, extract scalar values
                    reconstructed_cols = {}
                    for orig_col, measures in merged_dict.items():
                        for measure, value in measures.items():
                            col_name = json.dumps([orig_col, measure])
                            if measure == 'value_counts' and isinstance(value, pl.Series):
                                # Preserve the Series for value_counts (it's a Series of structs)
                                reconstructed_cols[col_name] = [value]
                            elif isinstance(value, pl.Series):
                                # For other Series, extract first element
                                scalar_val = value[0] if value.len() > 0 else None
                                reconstructed_cols[col_name] = [scalar_val]
                            elif isinstance(value, list):
                                scalar_val = value[0] if value else None
                                reconstructed_cols[col_name] = [scalar_val]
                            else:
                                reconstructed_cols[col_name] = [value]
                    
                    if reconstructed_cols:
                        res = pl.DataFrame(reconstructed_cols)
                    else:
                        res = pl.DataFrame()
            else:
                # If no expressions worked, create empty result with correct schema
                # This should rarely happen, but handle it gracefully
                res = pl.DataFrame()
        
        # Collect the original column data for column_ops execution
        original_data = only_cols.collect()
        # Build series stats from the selection result, passing actual data so column_ops can execute
        # Use run_computed_summary=True so computed_summary runs here (PAFColumnExecutor doesn't
        # call polars_produce_summary_df separately)
        series_stats, errs = polars_series_stats_from_select_result(
            res, original_data, self.analyses, 'paf_exec', debug=False, run_computed_summary=True
        )
        # Extract hash values from result if present
        hash_values: dict[str, int] = {}
        for c in cols:
            hcol = f"{c}_hash"
            if hcol in res.columns:
                try:
                    hash_values[c] = int(res[hcol][0])
                except Exception:
                    hash_values[c] = 0
            else:
                hash_values[c] = 0
        return self._series_stats_to_results(cols, series_stats, hash_values)

    def _series_stats_to_results(self,
                                 cols: list[str],
                                 series_stats: dict[str, dict[str, Any]],
                                 hash_values: dict[str, int]) -> ColumnResults:
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
            hash_val = hash_values.get(c, 0)
            per_col_stats = orig_to_stats.get(c, {})
            results[c] = ColumnResult(
                series_hash=hash_val,
                column_name=c,
                expressions=[],
                result=per_col_stats,
            )
        return results

