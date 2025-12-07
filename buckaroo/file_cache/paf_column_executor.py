from __future__ import annotations

from typing import Any, List, Type, Set
from collections import defaultdict
import json
import logging

import polars as pl

from buckaroo.file_cache.base import ColumnExecutor, ColumnResults, ColumnResult, ExecutorArgs
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysis, polars_select_expressions, polars_series_stats_from_select_result,
)
from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts


class PAFColumnExecutor(ColumnExecutor[ExecutorArgs]):
    """
    ColumnExecutor that delegates per-column analysis to the Polars pluggable
    analysis framework. It executes provided PolarsAnalysis classes to derive
    summary stats per column, and returns ColumnResults suitable for caching.
    """

    def __init__(self, analyses: List[Type[PolarsAnalysis]], cached_merged_sd: dict[str, dict[str, Any]] | None = None, orig_to_rw_map: dict[str, str] | None = None) -> None:
        self.analyses = list(analyses)
        self.cached_merged_sd = cached_merged_sd or {}
        self.orig_to_rw_map = orig_to_rw_map or {}
    
    def _get_expected_stat_keys(self) -> Set[str]:
        """
        Extract the stat keys that are guaranteed to be produced by the requested analyses.
        
        Returns a set of stat key names from provides_defaults of all analyses.
        
        NOTE: This is a conservative approach. We only check provides_defaults, not
        stat keys produced by select_clauses or column_ops. This means:
        - If a column has results from select_clauses but is missing some provides_defaults
          keys, we will re-execute the entire analysis class
        - This is intentional for now - we treat the implementation of how analyses
          produce their stats (select_clauses, column_ops, computed_summary) as a black box
        - Future improvements could integrate stat key extraction into the
          pluggable_analysis_framework itself
        
        This approach ensures correctness: if any expected stat key is missing,
        we re-execute to ensure all stats are present.
        """
        stat_keys: Set[str] = set()
        
        for analysis_class in self.analyses:
            # Only check provides_defaults - these are the guaranteed stat keys
            # that the analysis will produce
            if hasattr(analysis_class, 'provides_defaults'):
                defaults = analysis_class.provides_defaults
                if isinstance(defaults, dict):
                    stat_keys.update(defaults.keys())
        
        return stat_keys

    def get_execution_args(self, existing_stats:dict[str,dict[str,object]]) -> ExecutorArgs:
        # Check if ALL columns in this group are cached - if so, set no_exec=True
        # Otherwise, filter to only columns that need execution and set no_exec=False
        logger = logging.getLogger("buckaroo.paf_column_executor")
        
        all_input_cols = list(existing_stats.keys())
        columns_to_execute = []
        all_cached = True
        
        logger.info(f"PAFColumnExecutor.get_execution_args: checking {len(all_input_cols)} columns in group")
        logger.debug(f"  Input columns: {all_input_cols}")
        logger.debug(f"  cached_merged_sd keys: {list(self.cached_merged_sd.keys())}")
        logger.debug(f"  orig_to_rw_map: {self.orig_to_rw_map}")
        
        # Get expected stat keys from the requested analyses
        expected_stat_keys = self._get_expected_stat_keys()
        logger.debug(f"  Expected stat keys from analyses: {expected_stat_keys}")
        
        for orig_col in all_input_cols:
            rw_col = self.orig_to_rw_map.get(orig_col, orig_col)
            is_cached = False
            if rw_col in self.cached_merged_sd:
                cached_entry = self.cached_merged_sd[rw_col]
                if isinstance(cached_entry, dict):
                    cached_keys = set(cached_entry.keys())
                    basic_keys = {'orig_col_name', 'rewritten_col_name'}
                    cached_stat_keys = cached_keys - basic_keys
                    
                    # Check if column has real stats (more than just basic keys)
                    if len(cached_stat_keys) > 0:
                        # Check if all expected stat keys are present in cache
                        if expected_stat_keys:
                            # We have expected keys from provides_defaults - check if all are present
                            missing_keys = expected_stat_keys - cached_stat_keys
                            if not missing_keys:
                                # All expected stat keys are present
                                is_cached = True
                                logger.debug(f"  Column {orig_col} (rw: {rw_col}) is CACHED - has all expected stat keys: {expected_stat_keys}")
                            else:
                                # Some expected stat keys are missing - re-execute the entire analysis
                                # NOTE: We treat the analysis implementation (select_clauses, column_ops, computed_summary)
                                # as a black box. If provides_defaults indicates missing keys, we re-execute
                                # the entire analysis class to ensure all stats (including those from select_clauses
                                # and column_ops) are present. This is conservative but correct.
                                logger.debug(f"  Column {orig_col} (rw: {rw_col}) needs EXECUTION - missing stat keys: {missing_keys}")
                        else:
                            # No provides_defaults keys to check - we can't verify completeness
                            # Since we treat the analysis implementation (select_clauses, column_ops, etc.)
                            # as a black box, we can't know if all stats are present.
                            # Fall back to checking if column has any stats (backward compatibility)
                            # This is not ideal but necessary when analyses don't declare provides_defaults
                            is_cached = True
                            logger.debug(f"  Column {orig_col} (rw: {rw_col}) is CACHED (fallback) - has {len(cached_stat_keys)} stat keys, but no provides_defaults to verify completeness")
            
            if not is_cached:
                # Column needs execution
                all_cached = False
                columns_to_execute.append(orig_col)
                logger.debug(f"  Column {orig_col} (rw: {rw_col}) needs EXECUTION")
        
        # If all columns in this group are cached, set no_exec=True
        # Otherwise, filter to only columns that need execution
        no_exec = all_cached and len(all_input_cols) > 0
        
        logger.info(f"PAFColumnExecutor.get_execution_args: group has {len(all_input_cols)} columns, "
                   f"all_cached={all_cached}, no_exec={no_exec}, columns_to_execute={len(columns_to_execute)}")
        logger.debug(f"  To execute: {columns_to_execute}")
        
        # include hash only if any column (including cached ones) is marked missing via sentinel
        include_hash = any(
            bool(existing_stats.get(col, {}).get('__missing_hash__'))
            for col in all_input_cols
        )

        # Use the EXACT same expressions as regular PAF to ensure identical results
        # This ensures PAFColumnExecutor is a drop-in replacement for regular PAF
        expressions: list[pl.Expr] = polars_select_expressions(self.analyses)

        return ExecutorArgs(
            columns=columns_to_execute,  # Only columns that need execution (empty if all cached)
            column_specific_expressions=False,  # Using same expressions as regular PAF (not per-column)
            include_hash=include_hash,
            expressions=expressions,
            row_start=None,
            row_end=None,
            extra=None,
            no_exec=no_exec,  # True if all columns in this group are cached
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

