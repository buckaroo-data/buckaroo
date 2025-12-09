#!/usr/bin/env python
# coding: utf-8
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, Callable, TYPE_CHECKING
from pathlib import Path
import os
import logging
import threading

import polars as pl
import pandas as pd
from traitlets import Dict as TDict, Any as TAny, Unicode, observe

from .styling_core import merge_sds
from buckaroo.df_util import old_col_new_col
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.customizations.polars_analysis import PL_Analysis_Klasses
from buckaroo.file_cache.base import FileCache, ProgressNotification, ProgressListener, Executor, SimpleExecutorLog, ColumnExecutor as ColumnExecutorBase, MaybeFilepathLike
from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
from .abc_dataflow import ABCDataflow
from buckaroo.serialization_utils import pd_to_obj

logger = logging.getLogger("buckaroo.dataflow")

if TYPE_CHECKING:
    from buckaroo.file_cache.batch_planning import PlanningFunction


class ColumnExecutorDataflow(ABCDataflow):
    """A minimal DataFlow focused on column-executor-driven summary stats for Polars LazyFrames.

    - Works with a LazyFrame and avoids materializing the dataframe on load.

    - No-op command config, autocleaning, quick commands, and
      post-processing. Those don't work in the lazy world
      
    - Provides an explicit method to populate merged_sd rather than auto-observers.

    """

    # LazyFrame ref (not collected)
    raw_ldf = TAny()

    # Meta about the dataframe (computed lazily via aggregates)
    df_meta = TDict({
        'columns': 0,
        'rows_shown': 0,
        'filtered_rows': 0,
        'total_rows': 0
    }).tag(sync=True)

    # No-op configs (placeholders)
    command_config = TDict({}).tag(sync=True)
    quick_command_args = TDict({}).tag(sync=True)
    cleaning_method = Unicode('').tag(sync=True)
    post_processing_method = Unicode('').tag(sync=True)

    # Additional fields for widget compatibility
    buckaroo_options = TDict({}).tag(sync=True)
    operations = TAny([]).tag(sync=True)
    operation_results = TDict({'transformed_df': None, 'generated_py_code': ""}).tag(sync=True)
    df_display_args = TDict({}).tag(sync=True)
    df_data_dict = TDict({'empty': []}).tag(sync=True)
    widget_args_tuple = TAny()

    # Summary/processed/merged stats dictionaries (external code sets these)
    summary_sd = TAny({})
    cleaned_sd = TAny({})
    processed_sd = TAny({})
    merged_sd = TAny({})
    # Optional callback to stream progress summary updates
    progress_update_callback: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

    # Analysis classes (extendable, like CustomizableDataflow)
    analysis_klasses: List[Type[PolarsAnalysis]] = PL_Analysis_Klasses.copy()
    # Column executor class (overridable for testing or custom behavior)
    ColumnExecutorKlass: Type[ColumnExecutorBase] = PAFColumnExecutor

    def __init__(self, ldf: pl.LazyFrame, analysis_klasses: Optional[List[Type[PolarsAnalysis]]] = None,
                 column_executor_class: Optional[Type[ColumnExecutorBase]] = None,
                 executor_class: Optional[Type[Executor]] = None,
                 executor_log: Optional[SimpleExecutorLog] = None) -> None:
        super().__init__()
        self.raw_ldf = ldf
        if analysis_klasses is not None:
            self.analysis_klasses = list(analysis_klasses)
        self._column_executor_class: Type[ColumnExecutorBase] = column_executor_class or self.ColumnExecutorKlass
        self._executor_class: Type[Executor] = executor_class or Executor
        self.executor_log = executor_log or SimpleExecutorLog()
        self._initialize_df_meta()
        self.widget_args_tuple = (id(None), None, self.merged_sd)

    def _initialize_df_meta(self) -> None:
        """
        Populate df_meta using only lazy aggregates; do not materialize the dataframe.
        """
        try:
            total_rows = int(self.raw_ldf.select(pl.len().alias("__len")).collect().item())  # aggregate only
        except Exception:
            total_rows = 0
        cols = list(self.raw_ldf.collect_schema().names())
        self.df_meta = {
            'columns': len(cols),
            'rows_shown': 0,
            'filtered_rows': 0,
            'total_rows': total_rows
        }


    def add_analysis(self, analysis_klass: Type[PolarsAnalysis]) -> None:
        """
        Extend analysis_klasses set; deduplicate by cname.
        """
        existing = {ak.cname(): ak for ak in self.analysis_klasses}
        existing[analysis_klass.cname()] = analysis_klass
        self.analysis_klasses = list(existing.values())

    # Implement abstract method with local naming to match ABC
    def populate_df_meta(self) -> None:
        self._initialize_df_meta()

    def compute_summary_with_executor(
        self,
        file_cache: Optional[FileCache] = None,
        progress_listener: Optional[ProgressListener] = None,
        file_path: MaybeFilepathLike = None,
        planning_function: Optional["PlanningFunction"] = None,
        timeout_secs: Optional[float] = None,
        cached_merged_sd_override: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        Execute the PAF column executor over the LazyFrame to compute summary stats.
        - Avoids materializing the entire dataframe; executes per-column selections lazily.
        - Aggregates ColumnResults into a summary dict keyed by rewritten column names.
        - Sets summary_sd and populates merged_sd.
        """
        fc = file_cache or FileCache()
        
        # Build rewritten name mapping using an empty frame with the same columns
        empty_pl_df = pl.DataFrame({c: [] for c in self.raw_ldf.collect_schema().names()})
        orig_to_rw = dict(old_col_new_col(empty_pl_df))
        
        # Check if we have cached merged_sd to pass to column executor
        
        
        # Use override if provided (e.g., when adding new analysis)
        cached_merged_sd_for_executor = cached_merged_sd_override
        
        if cached_merged_sd_for_executor is None and file_path and fc:
            file_path_obj = Path(file_path)
            if fc.check_file(file_path_obj):
                md = fc.get_file_metadata(file_path_obj)
                if md and 'merged_sd' in md:
                    full_cached_merged_sd = md.get('merged_sd', {})
                    logger.info(f"ColumnExecutorDataflow.compute_summary_with_executor: loaded cached_merged_sd with {len(full_cached_merged_sd)} columns from file_path={file_path}")
                    logger.debug(f"  Full cached columns: {list(full_cached_merged_sd.keys())}")
                    
                    # Filter cached data to only include columns that exist in the current LazyFrame
                    # The cache may contain columns from a different column subset
                    # Cache entries are keyed by rewritten names from the full dataframe, but we need to
                    # match by original column names since rewritten names change based on column order
                    current_orig_cols = set(orig_to_rw.keys())
                    cached_merged_sd_for_executor = {}
                    
                    for cached_rw_col, cached_stats in full_cached_merged_sd.items():
                        if isinstance(cached_stats, dict):
                            cached_orig_col = cached_stats.get('orig_col_name')
                            if cached_orig_col and cached_orig_col in current_orig_cols:
                                # This column exists in current LazyFrame - map it to its new rewritten name
                                new_rw_col = orig_to_rw.get(cached_orig_col)
                                if new_rw_col:
                                    # Copy the stats and update the rewritten_col_name to match the new mapping
                                    stats_copy = cached_stats.copy()
                                    stats_copy['rewritten_col_name'] = new_rw_col
                                    cached_merged_sd_for_executor[new_rw_col] = stats_copy
                    
                    if len(cached_merged_sd_for_executor) < len(full_cached_merged_sd):
                        filtered_count = len(full_cached_merged_sd) - len(cached_merged_sd_for_executor)
                        logger.info(f"  Filtered cached data: kept {len(cached_merged_sd_for_executor)}/{len(full_cached_merged_sd)} columns (removed {filtered_count} columns not in current LazyFrame)")
                        logger.debug(f"  Filtered cached columns: {list(cached_merged_sd_for_executor.keys())}")
                    else:
                        logger.info(f"  Using all {len(cached_merged_sd_for_executor)} cached columns")
                else:
                    logger.info(f"ColumnExecutorDataflow.compute_summary_with_executor: no merged_sd in cache for file_path={file_path}")
            else:
                logger.info(f"ColumnExecutorDataflow.compute_summary_with_executor: file not in cache: {file_path}")
        else:
            logger.info("ColumnExecutorDataflow.compute_summary_with_executor: no file_path or fc provided")
        
        logger.info(f"ColumnExecutorDataflow.compute_summary_with_executor: orig_to_rw map has {len(orig_to_rw)} columns: {list(orig_to_rw.keys())[:5]}...")
        
        # Pass cached_merged_sd and orig_to_rw_map to column executor so it can set no_exec flag
        column_executor = self._column_executor_class(
            self.analysis_klasses,
            cached_merged_sd=cached_merged_sd_for_executor,
            orig_to_rw_map=orig_to_rw
        )

        # Start with cached merged_sd if available (so skipped columns are included in aggregated_summary)
        # Note: cached_merged_sd_for_executor is already filtered to only include columns in the current LazyFrame
        aggregated_summary: Dict[str, Dict[str, Any]] = {}
        if cached_merged_sd_for_executor:
            # Initialize with cached data so skipped columns are preserved
            for rw_col, cached_stats in cached_merged_sd_for_executor.items():
                if isinstance(cached_stats, dict):
                    aggregated_summary[rw_col] = cached_stats.copy()

        dataflow_id = id(self)
        dataflow_pid = os.getpid()
        log_msg = f"ColumnExecutorDataflow.compute_summary_with_executor: Dataflow created - dataflow_id={dataflow_id}, pid={dataflow_pid}"
        logger.info(log_msg)
        
        def _listener(note: ProgressNotification) -> None:
            current_pid = os.getpid()
            current_dataflow_id = id(self)
            current_thread_id = threading.get_ident()
            log_msg = f"ColumnExecutorDataflow._listener: dataflow_id={current_dataflow_id}, pid={current_pid}, thread_id={current_thread_id}, original_dataflow_id={dataflow_id}, original_pid={dataflow_pid}, col_group={note.col_group}, success={note.success}, result_keys={list(note.result.keys()) if note.result else None}"
            logger.info(log_msg)
            # Chain to upstream listener if provided
            if progress_listener:
                try:
                    log_msg2 = f"ColumnExecutorDataflow._listener: Calling upstream progress_listener - dataflow_id={current_dataflow_id}, thread_id={current_thread_id}"
                    logger.info(log_msg2)
                    progress_listener(note)
                    log_msg3 = f"ColumnExecutorDataflow._listener: Upstream progress_listener returned - dataflow_id={current_dataflow_id}, thread_id={current_thread_id}"
                    logger.info(log_msg3)
                except Exception as e:
                    log_msg_err = f"ColumnExecutorDataflow._listener: Exception calling upstream listener - dataflow_id={current_dataflow_id}, thread_id={current_thread_id}, error={e}"
                    logger.exception(log_msg_err)
            if not note.success or note.result is None:
                # Log failures so we can diagnose issues
                logger.warning(f"Column group {note.col_group} failed: {note.failure_message}")
                # Mark columns as error status
                for col in note.col_group:
                    rw = orig_to_rw.get(col, col)
                    entry = aggregated_summary.get(rw)
                    if entry is None:
                        entry = {'orig_col_name': col, 'rewritten_col_name': rw}
                        aggregated_summary[rw] = entry
                    entry['__status__'] = 'error'
                return
            # note.result is ColumnResults: Dict[str, ColumnResult] keyed by ORIGINAL column names
            for orig_col, col_res in note.result.items():
                stats = col_res.result or {}
                rw = orig_to_rw.get(orig_col, orig_col)
                entry = aggregated_summary.get(rw)
                if entry is None:
                    entry = {'orig_col_name': orig_col, 'rewritten_col_name': rw}
                    aggregated_summary[rw] = entry
                entry.update(stats)
                # Remove pending status on successful computation
                entry.pop('__status__', None)
            # Stream partial updates via callback and local df_data_dict for consumers
            try:
                if self.progress_update_callback:
                    # Merge with existing merged_sd so cached columns are preserved
                    current_merged = self.merged_sd.copy() if self.merged_sd else {}
                    merged_summary = current_merged.copy()
                    merged_summary.update(aggregated_summary)
                    log_msg2 = f"ColumnExecutorDataflow._listener: Calling progress_update_callback - dataflow_id={current_dataflow_id}, pid={current_pid}, thread_id={current_thread_id}, columns_in_summary={len(merged_summary)}, callback_id={id(self.progress_update_callback)}"
                    logger.info(log_msg2)
                    self.progress_update_callback(merged_summary)
                    log_msg3 = f"ColumnExecutorDataflow._listener: progress_update_callback returned - dataflow_id={current_dataflow_id}, thread_id={current_thread_id}"
                    logger.info(log_msg3)
                else:
                    log_msg_no_callback = f"ColumnExecutorDataflow._listener: No progress_update_callback set - dataflow_id={current_dataflow_id}, thread_id={current_thread_id}"
                    logger.warning(log_msg_no_callback)
                # keep local df_data_dict updated too
                if isinstance(aggregated_summary, dict) and len(aggregated_summary) > 0:
                    # Merge with existing to preserve cached columns
                    current_summary = self.summary_sd.copy() if self.summary_sd else {}
                    current_summary.update(aggregated_summary)
                    self.summary_sd = current_summary
                    rows = pd_to_obj(pd.DataFrame(current_summary))
                    self.df_data_dict = {'main': [], 'all_stats': rows, 'empty': []}
                    # Update merged_sd as stats come in (important for async executors)
                    # Merge with existing to preserve any cached columns
                    current_merged = self.merged_sd.copy() if self.merged_sd else {}
                    current_merged.update(merge_sds(self.cleaned_sd or {}, self.summary_sd or {}, self.processed_sd or {}))
                    self.merged_sd = current_merged
            except Exception:
                # do not interrupt execution on progress update failures
                pass

        listener_id = id(_listener)
        # Pass timeout_secs to MultiprocessingExecutor if provided
        # Only pass timeout_secs if it's MultiprocessingExecutor and timeout is provided
        if timeout_secs is not None and issubclass(self._executor_class, MultiprocessingExecutor):
            ex = self._executor_class(
                self.raw_ldf, 
                column_executor, 
                _listener, 
                fc, 
                executor_log=self.executor_log, 
                file_path=file_path,
                timeout_secs=timeout_secs,
                cached_merged_sd=cached_merged_sd_for_executor,
                orig_to_rw_map=orig_to_rw,
                planning_function=planning_function
            )
        else:
            ex = self._executor_class(
                self.raw_ldf, 
                column_executor, 
                _listener, 
                fc, 
                executor_log=self.executor_log, 
                file_path=file_path,
                cached_merged_sd=cached_merged_sd_for_executor,
                orig_to_rw_map=orig_to_rw,
                planning_function=planning_function
            )
        executor_id = id(ex)
        executor_pid = os.getpid()
        log_msg = f"ColumnExecutorDataflow.compute_summary_with_executor: Executor created - executor_id={executor_id}, executor_class={self._executor_class.__name__}, pid={executor_pid}, dataflow_id={dataflow_id}, dataflow_pid={dataflow_pid}, listener_id={listener_id}"
        logger.info(log_msg)
        ex.run()

        # Save and merge (no helper method; set properties directly)
        # Note: For async executors, merged_sd may already be updated by the progress callback above
        # aggregated_summary now includes cached columns (initialized above) + newly computed ones
        if aggregated_summary and len(aggregated_summary) > 0:
            self.summary_sd = aggregated_summary
            self.merged_sd = merge_sds(self.cleaned_sd or {}, self.summary_sd or {}, self.processed_sd or {})
        # Otherwise, keep existing merged_sd (which may have cached data)
        
        # Save merged_sd to cache if we have a file_path and aggregated_summary has content
        if file_path and fc and aggregated_summary and len(aggregated_summary) > 0:
            try:
                fc.upsert_file_metadata(Path(file_path), {'merged_sd': self.merged_sd})
            except Exception as e:
                logger.warning(f"Failed to save merged_sd to cache: {e}")
        
        return None

    def auto_compute_summary(
        self,
        sync_executor_class: Type[Executor],
        parallel_executor_class: Type[Executor],
        num_rows_threshold: int = 300,
        num_cols_threshold: int = 50,
        file_cache: Optional[FileCache] = None,
        progress_listener: Optional[ProgressListener] = None,
        file_path: MaybeFilepathLike = None,
        planning_function: Optional["PlanningFunction"] = None,
        timeout_secs: Optional[float] = None,
        cached_merged_sd_override: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        # Determine shape
        try:
            total_rows = int(self.raw_ldf.select(pl.len().alias("__len")).collect().item())
        except Exception:
            total_rows = 0
        num_cols = len(self.raw_ldf.collect_schema().names())
        use_parallel = (total_rows >= num_rows_threshold) or (num_cols >= num_cols_threshold)
        # If sync was tried before and incomplete, force parallel
        dfi = (id(self.raw_ldf), "",)
        if self.executor_log.has_incomplete_for_executor(dfi, sync_executor_class.__name__):
            use_parallel = True
        exec_class = parallel_executor_class if use_parallel else sync_executor_class
        # Run
        self._executor_class = exec_class
        try:
            self.compute_summary_with_executor(
                file_cache=file_cache, 
                progress_listener=progress_listener, 
                file_path=file_path, 
                planning_function=planning_function, 
                timeout_secs=timeout_secs,
                cached_merged_sd_override=cached_merged_sd_override,
            )
        except Exception as e:
            #FIXME this is a place we want to send a progress notification about the failure or the different approach
            logger.warning(f"compute_summary_with_executor failed with {exec_class.__name__}: {e}", exc_info=True)
            
            # fallback to parallel on sync failure
            if exec_class is sync_executor_class:
                self._executor_class = parallel_executor_class
                try:
                    self.compute_summary_with_executor(
                        file_cache=file_cache, 
                        progress_listener=progress_listener, 
                        file_path=file_path, 
                        planning_function=planning_function, 
                        timeout_secs=timeout_secs,
                        cached_merged_sd_override=cached_merged_sd_override,
                    )
                except Exception as e2:
                    logger.error(f"compute_summary_with_executor also failed with parallel executor: {e2}", exc_info=True)
                    # Don't re-raise, let it fail silently and use defaults

    @property
    def processed_df(self) -> Any:
        return None

    @observe('merged_sd')
    def _on_merged_sd(self, _change) -> None:
        self.widget_args_tuple = (id(self.processed_df), self.processed_df, self.merged_sd)


