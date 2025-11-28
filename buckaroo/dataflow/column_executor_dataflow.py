#!/usr/bin/env python
# coding: utf-8
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, Callable

import polars as pl
from traitlets import Dict as TDict, Any as TAny, Unicode, observe

from .styling_core import merge_sds
from buckaroo.df_util import old_col_new_col
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.customizations.polars_analysis import PL_Analysis_Klasses
from buckaroo.file_cache.base import FileCache, ProgressNotification, ProgressListener, Executor, SimpleExecutorLog, ColumnExecutor as ColumnExecutorBase
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
from .abc_dataflow import ABCDataflow
from buckaroo.serialization_utils import pd_to_obj
import pandas as pd


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
    ) -> None:
        """
        Execute the PAF column executor over the LazyFrame to compute summary stats.
        - Avoids materializing the entire dataframe; executes per-column selections lazily.
        - Aggregates ColumnResults into a summary dict keyed by rewritten column names.
        - Sets summary_sd and populates merged_sd.
        """
        fc = file_cache or FileCache()
        column_executor = self._column_executor_class(self.analysis_klasses)

        # Build rewritten name mapping using an empty frame with the same columns
        empty_pl_df = pl.DataFrame({c: [] for c in self.raw_ldf.collect_schema().names()})
        orig_to_rw = dict(old_col_new_col(empty_pl_df))

        aggregated_summary: Dict[str, Dict[str, Any]] = {}

        def _listener(note: ProgressNotification) -> None:
            # Chain to upstream listener if provided
            if progress_listener:
                try:
                    progress_listener(note)
                except Exception:
                    pass
            if not note.success or note.result is None:
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
            # Stream partial updates via callback and local df_data_dict for consumers
            try:
                if self.progress_update_callback:
                    self.progress_update_callback(aggregated_summary)
                # keep local df_data_dict updated too
                if isinstance(aggregated_summary, dict) and len(aggregated_summary) > 0:
                    rows = pd_to_obj(pd.DataFrame(aggregated_summary))
                    self.df_data_dict = {'main': [], 'all_stats': rows, 'empty': []}
            except Exception:
                # do not interrupt execution on progress update failures
                pass

        ex = self._executor_class(self.raw_ldf, column_executor, _listener, fc, executor_log=self.executor_log)
        ex.run()

        # Save and merge (no helper method; set properties directly)
        self.summary_sd = aggregated_summary
        self.merged_sd = merge_sds(self.cleaned_sd or {}, self.summary_sd or {}, self.processed_sd or {})
        return None

    def auto_compute_summary(
        self,
        sync_executor_class: Type[Executor],
        parallel_executor_class: Type[Executor],
        num_rows_threshold: int = 300,
        num_cols_threshold: int = 50,
        file_cache: Optional[FileCache] = None,
        progress_listener: Optional[ProgressListener] = None,
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
            self.compute_summary_with_executor(file_cache=file_cache, progress_listener=progress_listener)
        except Exception:
            #FIXME this is a place we want to send a progress notification about the failure or the different approach

            
            # fallback to parallel on sync failure
            if exec_class is sync_executor_class:
                self._executor_class = parallel_executor_class
                self.compute_summary_with_executor(file_cache=file_cache, progress_listener=progress_listener)

    @property
    def processed_df(self) -> Any:
        return None

    @observe('merged_sd')
    def _on_merged_sd(self, _change) -> None:
        self.widget_args_tuple = (id(self.processed_df), self.processed_df, self.merged_sd)


