#!/usr/bin/env python
# coding: utf-8
from __future__ import annotations
import copy
import datetime
from datetime import timedelta
from typing import Any, Dict, List, Optional, Type
from io import BytesIO
from pathlib import Path
import os
import traceback
import re
import sys


import anywidget
import polars as pl
from polars import functions as F
import pandas as pd
import logging
from traitlets import Dict as TDict, Unicode

from .dataflow.column_executor_dataflow import ColumnExecutorDataflow
from .customizations.polars_analysis import PL_Analysis_Klasses, NOT_STRUCTS
from buckaroo.pluggable_analysis_framework.utils import json_postfix
from buckaroo.styling_helpers import obj_, pinned_histogram
from .pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from .df_util import old_col_new_col
from .serialization_utils import pd_to_obj
from buckaroo.file_cache.base import AbstractFileCache, Executor as _SyncExec, ExecutorLog  # type: ignore
from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor as _ParExec
from buckaroo.file_cache.cache_utils import get_global_file_cache, get_global_executor_log
from buckaroo.file_cache.batch_planning import default_planning_function, PlanningFunction



logger = logging.getLogger("buckaroo.widget")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[buckaroo] %(message)s"))
    logger.addHandler(_h)
#logger.setLevel(logging.INFO)

# To quiet logs in notebooks, set the logging level to WARNING or ERROR:
# import logging
# logging.getLogger("buckaroo").setLevel(logging.WARNING)  # or logging.ERROR

class SimpleAnalysis(PolarsAnalysis):


    provides_defaults = {'length':2, 'null_count':3, 'unique_count':5, 'empty_count':8}
    select_clauses = [
        (NOT_STRUCTS.len() - NOT_STRUCTS.is_duplicated().sum()).name.map(json_postfix('unique_count')),
        F.all().len().name.map(json_postfix('length')),
        F.col(pl.Utf8).str.count_matches("^$").sum().name.map(json_postfix('empty_count')),
        F.all().null_count().name.map(json_postfix('null_count'))]
    

def _extract_file_path_from_lazyframe(ldf: pl.LazyFrame) -> Optional[str]:
    """
    Attempt to extract the file path from a Polars LazyFrame.
    
    This works by inspecting the optimized plan string, which contains
    the file path for scan_parquet, scan_csv, etc. operations.
    
    Returns the file path if found, None otherwise.
    """
    try:
        # Get the optimized plan as a string
        plan_str = ldf.describe_optimized_plan()
        
        # Look for scan_parquet, scan_csv, scan_ipc, scan_ndjson patterns
        # Pattern: scan_parquet("/path/to/file.parquet")
        patterns = [
            r'scan_parquet\("([^"]+)"\)',
            r'scan_csv\("([^"]+)"\)',
            r'scan_ipc\("([^"]+)"\)',
            r'scan_ndjson\("([^"]+)"\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, plan_str)
            if match:
                file_path = match.group(1)
                # Verify the file exists
                if os.path.exists(file_path):
                    logger.info(f"Extracted file_path from LazyFrame: {file_path}")
                    return file_path
                else:
                    logger.warning(f"Extracted file_path from LazyFrame but file doesn't exist: {file_path}")
        
        logger.debug(f"Could not extract file_path from LazyFrame plan: {plan_str[:200]}...")
        return None
    except Exception as e:
        logger.debug(f"Failed to extract file_path from LazyFrame: {e}")
        return None


class LazyInfinitePolarsBuckarooWidget(anywidget.AnyWidget):
    """
    A lazy, infinite-viewer widget for Polars LazyFrame built on ColumnExecutorDataflow.
    - Summary stats via ColumnExecutorDataflow + PAF executor
    - Infinite row streaming directly from the LazyFrame
    - Minimal DFViewer config (no code interpreter/post-processing)
    """

    _esm = Path(__file__).parent / "static" / "widget.js"
    _css = Path(__file__).parent / "static" / "compiled.css"
    render_func_name = Unicode("DFViewerInfinite").tag(sync=True)
    
    def _log_cache_info(self, cached_sd: Dict[str, Dict[str, Any]], show_message_box: bool) -> None:
        """Calculate and log cache information."""
        if not show_message_box or not cached_sd or len(cached_sd) == 0:
            return
        
        # Calculate cache info
        total_stats = 0
        for col_stats in cached_sd.values():
            if isinstance(col_stats, dict):
                # Count non-metadata keys
                basic_keys = {'orig_col_name', 'rewritten_col_name', '__status__'}
                stat_keys = set(col_stats.keys()) - basic_keys
                total_stats += len(stat_keys)
        
        # Estimate cache size (rough approximation)
        cache_size_bytes = sys.getsizeof(str(cached_sd))
        cache_size_kb = cache_size_bytes / 1024
        
        stats_per_column = total_stats // len(cached_sd) if cached_sd else 0
        self._add_message('cache_info', 
                    f'Cache info. {len(cached_sd)} columns in cache, {stats_per_column} stats per column, total cache size {cache_size_kb:.1f} kilobytes',
                    show_message_box)
    
    def _add_message(self, msg_type: str, message: str, show_message_box: bool, **kwargs) -> None:
        """Add a message to the message log if message box is enabled."""
        # Check both the parameter and the trait value
        msg_box_enabled = show_message_box or (self.show_message_box.get('enabled', False) if isinstance(self.show_message_box, dict) else False)
        logger.debug(f"LazyInfinitePolarsBuckarooWidget._add_message: called with show_message_box={show_message_box}, trait={self.show_message_box}, enabled={msg_box_enabled}, msg_type={msg_type}, message={message[:100]}")
        if not msg_box_enabled:
            return
        # Get current messages - need to create a new list to trigger traitlets change
        current_messages = list(self.message_log.get('messages', []))
        msg_entry = {
            'time': datetime.datetime.now().isoformat(),
            'type': msg_type,
            'message': message,
            **kwargs
        }
        current_messages.append(msg_entry)
        # Keep only last 1000 messages to avoid memory issues
        if len(current_messages) > 1000:
            current_messages = current_messages[-1000:]
        # Create completely new dict with new list to ensure traitlets detects the change
        new_message_log = {'messages': list(current_messages)}
        logger.debug(f"LazyInfinitePolarsBuckarooWidget._add_message: updating message_log with {len(current_messages)} messages")
        # Set the trait - traitlets should detect the dict change Use notify_change to ensure the frontend is notified
        self.message_log = new_message_log
        # Force notification by accessing the trait
        _ = self.message_log
        # Verify it was set
        actual_count = len(self.message_log.get('messages', []))
        logger.debug(f"LazyInfinitePolarsBuckarooWidget._add_message: message_log trait updated, message count: {actual_count}")
        if actual_count != len(current_messages):
            logger.warning(f"LazyInfinitePolarsBuckarooWidget._add_message: Mismatch! Expected {len(current_messages)} messages, got {actual_count}")
    
    def _load_and_filter_cached_data(
        self,
        all_cols: List[str],
        show_message_box: bool,
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Load cached data from file cache, filter to match current LazyFrame columns, and log messages.
        
        Returns:
            Filtered cached merged_sd dict, or None if no cache available.
        """
        if not self._file_path or not self._file_cache:
            logger.info("LazyInfinitePolarsBuckarooWidget._load_and_filter_cached_data: No file_path or file_cache provided")
            return None
        
        file_path_obj = Path(self._file_path)
        # Check if file is in cache and hasn't been modified
        if self._file_cache.check_file(file_path_obj):
            self._add_message('cache', f'file found in cache with file name {self._file_path}', show_message_box)
            md = self._file_cache.get_file_metadata(file_path_obj)
            if md and 'merged_sd' in md:
                full_cached_merged_sd = md['merged_sd']
                logger.info(f"LazyInfinitePolarsBuckarooWidget._load_and_filter_cached_data: Loaded cached merged_sd for {self._file_path}")
                logger.info(f"  Full cached columns count: {len(full_cached_merged_sd)}")
                logger.debug(f"  Full cached column keys: {list(full_cached_merged_sd.keys())}")
                
                # Filter cached data to only include columns that exist in the current LazyFrame
                # The cache may contain columns from a different column subset, so we filter it
                # Cache entries are keyed by rewritten names from the full dataframe, but we need to
                # match by original column names since rewritten names change based on column order
                current_orig_cols = set(all_cols)
                cached_merged_sd = {}
                
                for cached_rw_col, cached_stats in full_cached_merged_sd.items():
                    if isinstance(cached_stats, dict):
                        cached_orig_col = cached_stats.get('orig_col_name')
                        if cached_orig_col and cached_orig_col in current_orig_cols:
                            # This column exists in current LazyFrame - map it to its new rewritten name
                            new_rw_col = self._orig_to_rw.get(cached_orig_col)
                            if new_rw_col:
                                # Copy the stats and update the rewritten_col_name to match the new mapping
                                stats_copy = cached_stats.copy()
                                stats_copy['rewritten_col_name'] = new_rw_col
                                cached_merged_sd[new_rw_col] = stats_copy
                
                if len(cached_merged_sd) < len(full_cached_merged_sd):
                    filtered_count = len(full_cached_merged_sd) - len(cached_merged_sd)
                    logger.info(f"  Filtered cached data: kept {len(cached_merged_sd)}/{len(full_cached_merged_sd)} columns (removed {filtered_count} columns not in current LazyFrame)")
                    logger.debug(f"  Filtered column keys: {list(cached_merged_sd.keys())}")
                else:
                    logger.info(f"  Using all {len(cached_merged_sd)} cached columns")
                
                # Log cache info if message box is enabled
                self._log_cache_info(cached_merged_sd, show_message_box)
                return cached_merged_sd
            else:
                logger.info(f"LazyInfinitePolarsBuckarooWidget._load_and_filter_cached_data: File in cache but no merged_sd for {self._file_path}")
                return None
        else:
            self._add_message('cache', f'file not found in cache for file name {self._file_path}', show_message_box)
            logger.info(f"LazyInfinitePolarsBuckarooWidget._load_and_filter_cached_data: File not in cache: {self._file_path}")
            return None
    
    def _log_execution_update(self, progress_note, show_message_box: bool) -> None:
        """Log execution update message to message box if enabled."""
        # Check both the parameter and the trait value
        msg_box_enabled = show_message_box or (self.show_message_box.get('enabled', False) if isinstance(self.show_message_box, dict) else False)
        if not msg_box_enabled:
            return
        
        status_str = "started" if progress_note.success and progress_note.result is None else ("finished" if progress_note.success else "error")
        time_str = datetime.datetime.now().isoformat()
        pid = os.getpid()
        num_cols = len(progress_note.col_group) if progress_note.col_group else 0
        num_expressions = len(progress_note.execution_args.expressions) if hasattr(progress_note.execution_args, 'expressions') and progress_note.execution_args.expressions else 0
        explicit_cols = progress_note.col_group if progress_note.col_group else []
        
        exec_time_secs = None
        if progress_note.success and hasattr(progress_note, 'execution_time') and progress_note.execution_time:
            if isinstance(progress_note.execution_time, timedelta):
                exec_time_secs = progress_note.execution_time.total_seconds()
            else:
                exec_time_secs = progress_note.execution_time
        
        msg_data = {
            'time_start': time_str,
            'pid': pid,
            'status': status_str,
            'num_columns': num_cols,
            'num_expressions': num_expressions,
            'explicit_column_list': explicit_cols,
        }
        if exec_time_secs is not None:
            msg_data['execution_time_secs'] = exec_time_secs
        
        try:
            logger.info(f"LazyInfinitePolarsBuckarooWidget._log_execution_update: calling _add_message for {status_str} with {num_cols} columns")
            self._add_message('execution', f'Execution update: {status_str}', show_message_box, **msg_data)
        except Exception as e:
            logger.warning(f"Failed to add execution message: {e}", exc_info=True)
    
    def _log_with_widget_info(self, message: str, include_current: bool = False, **kwargs) -> None:
        """
        Log a message with widget ID and PID tracking information.
        
        Args:
            message: The log message to format
            include_current: If True, includes current widget_id and pid for comparison with original
            **kwargs: Additional key-value pairs to include in the log message
        """
        widget_logger = logging.getLogger("buckaroo.lazy_widget")
        
        # Build base info with original widget tracking
        base_info = f"widget_id={self._original_widget_id}, pid={self._original_widget_pid}"
        
        if include_current:
            current_widget_id = id(self)
            current_pid = os.getpid()
            base_info += f", current_widget_id={current_widget_id}, current_pid={current_pid}"
        
        # Add any additional kwargs
        if kwargs:
            extra_info = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            full_message = f"{message}: {base_info}, {extra_info}"
        else:
            full_message = f"{message}: {base_info}"
        
        widget_logger.info(full_message)
    
    def ensure_file_path(
        self,
        file_path: Optional[str],
        ldf: pl.LazyFrame
    ) -> None:
        # Set file_path from parameter or extract from LazyFrame
        if file_path is None:
            extracted_path = _extract_file_path_from_lazyframe(ldf)
            if extracted_path:
                self._file_path = extracted_path
                logger.info(f"Auto-detected file_path from LazyFrame: {self._file_path}")
            else:
                self._file_path = None
                logger.info("Could not auto-detect file_path from LazyFrame, cache may not be used")
        else:
            self._file_path = file_path

    
    def ensure_file_cache(
        self,
        file_cache: Optional["AbstractFileCache"]
    ) -> None:
        # Set file_cache from parameter or use global cache
        if file_cache is None:
            self._file_cache = get_global_file_cache()
        else:
            self._file_cache = file_cache
            
    
    def ensure_df_meta(self, ldf: pl.LazyFrame, all_cols: List[str]) -> None:
        """
        Ensure that self.df_meta is set with column count and total row count.
        
        Calculates total_rows from the LazyFrame directly (avoiding constructing dataflow solely for meta)
        and sets df_meta with columns, rows_shown, filtered_rows, and total_rows.
        """
        # First-pass meta from polars directly (avoiding constructing dataflow solely for meta)
        try:
            total_rows = int(ldf.select(pl.len().alias("__len")).collect().item())
        except Exception:
            total_rows = 0
        num_cols = len(all_cols)
        
        self.df_meta = {'columns': num_cols, 'rows_shown': 0, 'filtered_rows': 0, 'total_rows': total_rows}
    
    def ensure_summary_defaults(self, all_cols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Prepare initial defaults so pinned rows have placeholders immediately.
        
        Creates a dictionary mapping rewritten column names to summary entries with:
        - orig_col_name and rewritten_col_name
        - __status__ set to 'pending'
        - Default values from all analysis classes' provides_defaults
        
        Returns:
            Dictionary mapping rewritten column names to their initial summary entries.
        """
        base: Dict[str, Dict[str, Any]] = {}
        for orig in all_cols:
            rw = self._orig_to_rw.get(orig, orig)
            entry: Dict[str, Any] = {
                'orig_col_name': orig,
                'rewritten_col_name': rw,
                '__status__': 'pending',  # 'pending', 'error', or default (computed)
            }
            for ak in self._analyses:
                try:
                    defaults = getattr(ak, 'provides_defaults', {}) or {}
                    if isinstance(defaults, dict):
                        entry.update(defaults)
                except Exception:
                    continue
            base[rw] = entry
        logger.info(f"LazyInfinitePolarsBuckarooWidget.ensure_summary_defaults: created {len(base)} entries, sample entry keys: {list(list(base.values())[0].keys()) if base else []}")
        return base
    
    def ensure_merged_initial_summary(
        self,
        initial_sd: Dict[str, Dict[str, Any]],
        cached_merged_sd: Optional[Dict[str, Dict[str, Any]]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge cached summary data into initial summary defaults.
        
        This ensures ALL columns are visible immediately (cached columns with real stats,
        uncached columns with defaults). The function:
        1. Starts with a copy of initial_sd (defaults for all columns)
        2. Merges in cached stats where available
        3. Handles __status__ field appropriately (removes if cached data has real stats)
        4. Logs cache status for debugging
        
        Args:
            initial_sd: Initial summary defaults for all columns
            cached_merged_sd: Optional cached summary data (already filtered to current LazyFrame columns)
        
        Returns:
            Merged summary dictionary with cached stats where available, defaults otherwise.
        """
        # Start with initial defaults for all columns, then merge in cached data
        # This ensures ALL columns are visible immediately (cached columns with real stats,
        # uncached columns with defaults)
        initial_summary_sd = initial_sd.copy()
        
        if cached_merged_sd is not None and len(cached_merged_sd) > 0:
            # Merge cached data into initial summary so all columns appear, with cached stats where available
            # Note: cached_merged_sd is already filtered to only include columns in the current LazyFrame
            for col_name, cached_stats in cached_merged_sd.items():
                if col_name in initial_summary_sd:
                    # Preserve __status__ from initial if cached data doesn't have real stats
                    # If cached data has real stats (more than just basic keys), remove __status__
                    cached_keys = set(cached_stats.keys()) if isinstance(cached_stats, dict) else set()
                    basic_keys = {'orig_col_name', 'rewritten_col_name', '__status__'}
                    has_real_stats = len(cached_keys - basic_keys) > 0
                    
                    initial_summary_sd[col_name].update(cached_stats)
                    # If cached data has real stats, remove pending status (it's computed)
                    if has_real_stats:
                        initial_summary_sd[col_name].pop('__status__', None)
                    # If no real stats, keep the pending status from initial
                # Don't add columns that aren't in initial_summary_sd - they don't belong in this widget
            
            # Log cache status for debugging
            expected_cols = set(self._orig_to_rw.values())
            cached_cols_count = 0
            for rw_col, cached_entry in cached_merged_sd.items():
                if isinstance(cached_entry, dict):
                    keys = set(cached_entry.keys())
                    basic_keys = {'orig_col_name', 'rewritten_col_name'}
                    if keys > basic_keys and len(keys) > 2:
                        cached_cols_count += 1
            
            if cached_cols_count > 0:
                logger.info(f"Loaded {cached_cols_count}/{len(expected_cols)} columns from cache, computing remaining columns in background")
        
        return initial_summary_sd
    
    def ensure_initial_summary_for_display(
        self,
        initial_summary_sd: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Ensure summary data is ready for initial display with proper status markers and caching.
        
        Uses self._df.merged_sd if it has content (which may have been updated by auto_compute_summary
        if computation completed synchronously, or may still be the initial summary if computation
        is running asynchronously). Ensures __status__ markers are present for columns that only
        have defaults, and saves the summary to cache if available.
        
        If self._df.merged_sd is empty, falls back to initial_summary_sd.
        
        Args:
            initial_summary_sd: Initial summary dictionary with defaults and cached data
        
        Returns:
            Summary dictionary ready for display (either from merged_sd or initial_summary_sd)
        """
        # Important: DFViewer renders pinned-top rows by extracting values from
        # summary_stats_data using the configured pinned_rows (e.g., "unique_count",
        # "null_count"). If summary_stats_data is empty at first render (timeouts or
        # background execution), AG‑Grid has nothing to pin and the pinned area will
        # not appear. We seed summary_sd with _initial_sd (built from provides_defaults)
        # so all_stats has placeholders immediately and the pinned rows render even
        # before the background computation completes.
        # Use merged_sd if it has content, otherwise fall back to initial defaults
        # Make sure __status__ is preserved for columns that haven't been computed yet
        if self._df.merged_sd and len(self._df.merged_sd) > 0:
            summary_sd = self._df.merged_sd.copy()
            # Ensure __status__ is present for columns that only have defaults
            for col_name, col_stats in summary_sd.items():
                if isinstance(col_stats, dict):
                    # Check if column has real stats (more than just basic keys + defaults)
                    keys = set(col_stats.keys())
                    basic_keys = {'orig_col_name', 'rewritten_col_name', '__status__'}
                    stat_keys = keys - basic_keys
                    # If no real stats and no __status__, add pending status
                    if len(stat_keys) == 0 and '__status__' not in col_stats:
                        # Check if this looks like it only has defaults (no real computation)
                        # If it has provides_defaults values but they're all the same/default, it's pending
                        col_stats['__status__'] = 'pending'
            # Save merged_sd to cache for next time
            if self._file_path and self._file_cache:
                try:
                    self._file_cache.upsert_file_metadata(Path(self._file_path), {'merged_sd': summary_sd})
                except Exception as e:
                    logger.warning(f"Failed to save merged_sd to cache: {e}")
            return summary_sd
        else:
            # Fall back to initial summary which includes cached data if available
            return initial_summary_sd
    
    def ensure_df_display_args(
        self,
        all_cols: List[str],
        summary_sd: Dict[str, Dict[str, Any]],
        summary_rows: List[Dict[str, Any]]
    ) -> None:
        """
        Ensure that df_display_args and df_data_dict are set up for the widget.
        
        Builds the column configuration (from summary or schema fallback), creates the
        df_viewer_config with pinned rows, and sets both df_data_dict and df_display_args.
        
        Args:
            all_cols: List of all column names in the LazyFrame
            summary_sd: Summary dictionary with column statistics
            summary_rows: List of summary rows for display
        """
        # Build initial column_config: fall back to schema so raw data appears immediately.
        def _schema_column_config() -> list[dict[str, object]]:
            return [{
                "col_name": self._orig_to_rw.get(c, c),
                "header_name": c,
                "displayer_args": {"displayer": "obj"},
            } for c in all_cols]
        initial_col_config = self._build_column_config(summary_sd) if summary_sd else _schema_column_config()

        #fixme maybe the cache checking should be done by dataflow.
        self.df_data_dict = {'main': [], 'all_stats': summary_rows, 'empty': []}

        #FIXME,  this isn't showing any pinned rows
        df_viewer_config = {
            "pinned_rows": [
                obj_('dtype'),
                pinned_histogram(),
                {'primary_key_val': '__status__',     'displayer_args': {'displayer': 'obj' } },
                {'primary_key_val': 'unique_count',     'displayer_args': {'displayer': 'obj' } },
                {'primary_key_val': 'null_count',     'displayer_args': {'displayer': 'obj' } },
                {'primary_key_val': 'empty_count',     'displayer_args': {'displayer': 'obj' } },
            ],
            "column_config": initial_col_config,
            "left_col_configs": [{"col_name": "index", "header_name": "index", "displayer_args": {"displayer": "obj"}}],}
        
        logger.info("LazyInfinite init: total_rows=%s; initial columns=%s", self.df_meta['total_rows'], [c.get("header_name") for c in initial_col_config])
        logger.info(
            "Setting df_display_args with pinned_rows=%s",
            [pr.get("primary_key_val") for pr in df_viewer_config.get("pinned_rows", [])],
        )
        self.df_display_args = {
            'main': {
                'data_key': 'main',
                'df_viewer_config': df_viewer_config,
                'summary_stats_key': 'all_stats'
            }
        }

    # Traits consumed by DFViewerInfiniteDS
    df_meta = TDict({
        'columns': 0,
        'rows_shown': 0,
        'filtered_rows': 0,
        'total_rows': 0
    }).tag(sync=True)
    df_data_dict = TDict({'empty': []}).tag(sync=True)
    df_display_args = TDict({}).tag(sync=True)
    df_id = Unicode("unknown").tag(sync=True)

    # Progress from executor (plumbed via listener)
    executor_progress = TDict({}).tag(sync=True)
    
    # Message log for displaying execution updates, cache info, etc.
    message_log = TDict({'messages': []}).tag(sync=True)
    
    # Option to show message box
    show_message_box = TDict({'enabled': False}).tag(sync=True)

    def __init__(
        self,
        ldf: pl.LazyFrame,
        *,
        analysis_klasses: Optional[List[Type[PolarsAnalysis]]] = None,
        debug: bool = False,
        column_executor_class: Optional[type] = None,
        file_path: Optional[str] = None,
        file_cache: Optional["AbstractFileCache"] = None,
        executor_log: Optional[ExecutorLog] = None,
        sync_executor_class: Optional[type] = None,
        #don't need parallel_executor_class  
        parallel_executor_class: Optional[type] = None,
        planning_function: Optional["PlanningFunction"] = None,  # type: ignore
        timeout_secs: float = 10.0,  # Timeout for multiprocessing executor (default 120s for large files)
        show_message_box: bool = False,  # Enable message box for logging
    ) -> None:
        logger = logging.getLogger("buckaroo.lazy_widget")
        # Store original widget ID and PID for logging and tracking
        self._original_widget_id = id(self)
        self._original_widget_pid = os.getpid()
        self._log_with_widget_info("LazyInfinitePolarsBuckarooWidget.__init__ START", file_path=file_path)
        
        super().__init__()
        self._debug = debug
        self._ldf = ldf
        self.show_message_box = {'enabled': show_message_box}
        logger.info(f"LazyInfinitePolarsBuckarooWidget.__init__: show_message_box={show_message_box}, setting trait to {self.show_message_box}")
        default_analyses = PL_Analysis_Klasses
        #default_analyses = [SimpleAnalysis]

        self._analyses = list(analysis_klasses) if analysis_klasses is not None else default_analyses

        # Use global cache instances by default
        if executor_log is None:
            executor_log = get_global_executor_log()
        
        # Store parameters for add_analysis
        self._sync_executor_class = sync_executor_class
        self._parallel_executor_class = parallel_executor_class
        self._planning_function = planning_function
        self._timeout_secs = timeout_secs

        # Ensure file_cache is set
        self.ensure_file_cache(file_cache)
        
        # Ensure file_path is set, attempting to extract from LazyFrame if needed
        self.ensure_file_path(file_path, ldf)


        # Build stable rewrites
        # Try to get column names from schema, but handle errors gracefully
        # (e.g., corrupted parquet files in tests)
        try:
            all_cols = self._ldf.collect_schema().names()
        except Exception as e:
            logger.warning(f"Failed to collect schema from LazyFrame: {e}. This may indicate a corrupted file or unsupported format.")
            # If schema collection fails, we can't determine columns without reading the file
            # This will cause issues later, but we allow initialization to proceed
            # The widget will fail when trying to compute stats, but at least we've logged the error
            all_cols = []
        
        empty_pl_df = pl.DataFrame({c: [] for c in all_cols})
        self._orig_to_rw = dict(old_col_new_col(empty_pl_df))
        self._rw_to_orig = {v: k for k, v in self._orig_to_rw.items()}

        # Optional cache short-circuit
        cached_merged_sd = self._load_and_filter_cached_data(all_cols, show_message_box)

        # Ensure df_meta is set with column and row counts
        self.ensure_df_meta(ldf, all_cols)

        # Dataflow for summary stats with chosen executor
        self._df = ColumnExecutorDataflow(
            ldf,
            analysis_klasses=self._analyses,
            column_executor_class=column_executor_class,
            executor_log=executor_log)

        # Stream progress updates into df_data_dict so the UI reflects new stats as they arrive.
        # Keep track of initial merged_sd to preserve cached columns
        self._log_with_widget_info("LazyInfinitePolarsBuckarooWidget.__init__: Widget instance ready")
        
        def _on_progress_update(aggregated_summary: Dict[str, Dict[str, Any]]) -> None:
            self._log_with_widget_info(
                "LazyInfinitePolarsBuckarooWidget._on_progress_update",
                include_current=True,
                columns_in_update=len(aggregated_summary) if aggregated_summary else 0
            )
            try:
                # Merge with existing merged_sd to preserve cached columns
                # aggregated_summary may only contain newly computed columns
                current_merged = self._df.merged_sd.copy() if self._df.merged_sd else {}
                merged_for_display = current_merged.copy()
                merged_for_display.update(aggregated_summary or {})
                
                rows = self._summary_to_rows(merged_for_display)              
                # Update merged_sd on dataflow so it's in sync
                self._df.merged_sd = merged_for_display
                # Update df_data_dict - create new dict to trigger traitlets change notification
                self.df_data_dict = {'main': [], 'all_stats': rows, 'empty': []}
                # Save merged_sd to cache as stats come in (important for async executors)
                if self._file_path and self._file_cache and merged_for_display and len(merged_for_display) > 0:
                    try:
                        self._file_cache.upsert_file_metadata(Path(self._file_path), {'merged_sd': merged_for_display})
                    except Exception as e:
                        logger.warning(f"Failed to save merged_sd to cache during progress update: {e}")
            except Exception:
                logger.exception("error updating df_data_dict from progress")
        self._df.progress_update_callback = _on_progress_update

        # Prepare initial defaults so pinned rows have placeholders immediately
        _initial_sd = self.ensure_summary_defaults(all_cols)
        # Compute summary stats and wire progress to a trait
        def _listener(note):
            # Minimal progress surface; expand as needed

            # logger.info(
            #     "ProgressNotification for %s  status %s message %s",
            #     note.col_group, note.success, note.failure_message)

            self.executor_progress = {
                'success': note.success,
                'col_group': note.col_group,
                'message': note.failure_message or ''
            }
            
            self._log_execution_update(note, show_message_box)

        chosen_sync_exec = sync_executor_class or _SyncExec
        chosen_par_exec = parallel_executor_class or _ParExec
        
        # Merge cached data into initial summary so all columns appear with cached stats where available
        initial_summary_sd = self.ensure_merged_initial_summary(_initial_sd, cached_merged_sd)
        
        # Initialize dataflow with merged initial + cached summary so widget can render all columns immediately
        # The executor will update this as it computes missing columns
        self._df.merged_sd = initial_summary_sd.copy()
        self._df.summary_sd = initial_summary_sd.copy()
        
        # Always run computation - Executor.run() will check if all columns are cached
        # and skip execution entirely if so. Otherwise, it will process column groups
        # and skip individual cached columns. This allows:
        # 1. Cached columns to appear immediately
        # 2. Missing columns to compute in background
        # 3. No need to wait for all columns before showing anything
        # Use default_planning_function (smart batch planner) for optimal performance by default
        # Tests can override with simple_one_column_planning for deterministic behavior
        chosen_planning_function = planning_function or default_planning_function
        self._df.auto_compute_summary(
            chosen_sync_exec,
            chosen_par_exec,
            file_cache=self._file_cache,
            progress_listener=_listener,
            file_path=self._file_path,
            planning_function=chosen_planning_function,
            timeout_secs=timeout_secs,
        )
        
        # Ensure summary is ready for initial display (checks if computation completed synchronously)
        summary_sd = self.ensure_initial_summary_for_display(initial_summary_sd)
        summary_rows = self._summary_to_rows(summary_sd)
        logger.info(
            "Initial all_stats prepared: len=%s sample=%s",
            len(summary_rows),
            (summary_rows[0] if summary_rows else None),
        )
        # Check if __status__ is in the summary rows
        status_row = next((row for row in summary_rows if row.get('index') == '__status__'), None)
        logger.info(f"LazyInfinitePolarsBuckarooWidget.__init__: __status__ row present: {status_row is not None}, show_message_box trait: {self.show_message_box}, message_log messages count: {len(self.message_log.get('messages', []))}")

        # Ensure df_display_args and df_data_dict are set up
        self.ensure_df_display_args(all_cols, summary_sd, summary_rows)

        self.df_id = str(id(ldf))

        # Message bridge for infinite requests
        def payload_bridge(_unused_self, msg, _unused_buffers):
            if msg.get('type') == 'infinite_request':
                payload_args = msg['payload_args']
                try:
                    logger.info(
                        "infinite_request key=%s-%s-%s start=%s end=%s origEnd=%s",
                        payload_args.get('sourceName'),
                        payload_args.get('sort'),
                        payload_args.get('sort_direction'),
                        payload_args.get('start'),
                        payload_args.get('end'),
                        payload_args.get('origEnd'),
                    )
                except Exception:
                    logger.exception("error logging infinite_request")
                self._handle_payload_args(payload_args)
        self.on_msg(payload_bridge)


    # no schema-only column config helper needed for sync path

    def _summary_to_rows(self, summary: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not summary:
            return []
        df = pd.DataFrame(summary)
        rows = pd_to_obj(df)
        return rows

    # selection and retry now delegated to dataflow
    def _build_column_config(self, summary: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        column_config: List[Dict[str, Any]] = []
        for rw, meta in summary.items():
            col_name = rw
            header_name = str(meta.get('orig_col_name', rw))
            # Minimal displayers; could be improved using dtype if available
            column_config.append({
                "col_name": col_name,
                "header_name": header_name,
                "displayer_args": {"displayer": "obj"},
            })
        return column_config

    def _prepare_df_for_serialization(self, df: pl.DataFrame) -> pl.DataFrame:
        # Ensure 'index' present and rename data columns to rewritten names
        if 'index' not in df.columns:
            df = df.with_row_index(name='index')
        select_clauses: List[pl.Expr] = [pl.col('index')]
        for orig in self._orig_to_rw.keys():
            if orig in df.columns:
                rw = self._orig_to_rw.get(orig, orig)
                select_clauses.append(pl.col(orig).alias(rw))
        return df.select(select_clauses)

    def _to_parquet(self, df: pl.DataFrame) -> bytes:
        out = BytesIO()
        self._prepare_df_for_serialization(df).write_parquet(out, compression='uncompressed')
        out.seek(0)
        return out.read()

    def _handle_payload_args(self, new_payload_args: Dict[str, Any]) -> None:
        start, end = new_payload_args.get('start', 0), new_payload_args.get('end', 0)
        if start is None or end is None:
            return
        try:
            logger.info(
                "_handle_payload_args start=%s end=%s origEnd=%s sort=%s sort_direction=%s",
                start,
                end,
                new_payload_args.get('origEnd'),
                new_payload_args.get('sort'),
                new_payload_args.get('sort_direction'),
            )
            # create a derived lazyframe to avoid borrowing conflicts with background tasks
            base = self._ldf.select(pl.all())
            sort = new_payload_args.get('sort')
            if sort:
                orig_sort_col = self._rw_to_orig.get(sort, sort)
                sort_dir = new_payload_args.get('sort_direction')
                ascending = (sort_dir == 'asc')
                base = base.sort(orig_sort_col, descending=not ascending)
            slice_len = max(int(end) - int(start), 0)
            # Use a global, non-repeating index by offsetting with the slice start
            slice_df = (
                base.slice(int(start), slice_len)
                .with_row_index(name='index', offset=int(start))
                .collect()
            )
            logger.info(
                "sending slice [%s,%s) rows=%s total=%s",
                start, end, len(slice_df), self.df_meta['total_rows']
            )
            self.send({"type": "infinite_resp", 'key': new_payload_args, 'data': [], 'length': self.df_meta['total_rows']},
                      [self._to_parquet(slice_df)])

            second_pa = new_payload_args.get('second_request')
            if second_pa:
                s2, e2 = second_pa.get('start'), second_pa.get('end')
                if s2 is not None and e2 is not None:
                    slice2 = (
                        base.slice(int(s2), max(int(e2) - int(s2), 0))
                        .with_row_index(name='index', offset=int(s2))
                        .collect()
                    )
                    logger.info(
                        "sending second slice [%s,%s) rows=%s total=%s",
                        s2, e2, len(slice2), self.df_meta['total_rows']
                    )
                    self.send({"type": "infinite_resp", 'key': second_pa, 'data': [], 'length': self.df_meta['total_rows']},
                              [self._to_parquet(slice2)])
        except Exception as e:
            stack_trace = traceback.format_exc()
            self.send({"type": "infinite_resp", 'key': new_payload_args, 'data': [], 'error_info': stack_trace, 'length': 0}, [])
            logger.exception("error handling payload args: %s", e)

    def add_analysis(self, analysis_klass: Type[PolarsAnalysis], pinned_row_configs: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Add a new analysis class to the widget and trigger recomputation.
        
        Args:
            analysis_klass: The PolarsAnalysis class to add
            pinned_row_configs: Optional list of pinned row configs to add for this analysis.
                              Each config should be a dict with 'primary_key_val' and 'displayer_args'.
                              If None, no pinned rows are added for this analysis.
        
        After adding the analysis, the executor will recompute summary stats including
        the new analysis. The pinned_rows will be updated to include the new pinned row configs.
        """
        logger.info(f"LazyInfinitePolarsBuckarooWidget.add_analysis: Adding {analysis_klass.__name__}")
        
        # Add analysis to dataflow
        self._df.add_analysis(analysis_klass)
        self._analyses.append(analysis_klass)
        
        # Update pinned_rows if provided
        if pinned_row_configs:
            # Get current config (make a deep copy to avoid mutating the original)            
            current_display_args = copy.deepcopy(dict(self.df_display_args))
            current_config = current_display_args.get('main', {}).get('df_viewer_config', {})
            current_pinned_rows = current_config.get('pinned_rows', []).copy() if current_config.get('pinned_rows') else []
            
            # Add new pinned rows (avoid duplicates by checking primary_key_val)
            existing_keys = {pr.get('primary_key_val') for pr in current_pinned_rows if isinstance(pr, dict)}
            for pr_config in pinned_row_configs:
                pkey = pr_config.get('primary_key_val')
                if pkey and pkey not in existing_keys:
                    current_pinned_rows.append(pr_config)
                    logger.info(f"  Added pinned_row for {pkey}")
            
            # Create new df_display_args dict with updated pinned_rows
            # This ensures traitlets detects the change and syncs to frontend
            if 'main' not in current_display_args:
                current_display_args['main'] = {}
            if 'df_viewer_config' not in current_display_args['main']:
                current_display_args['main']['df_viewer_config'] = {}
            current_display_args['main']['df_viewer_config']['pinned_rows'] = current_pinned_rows
            
            # Reassign entire dict to trigger traitlets change notification
            self.df_display_args = current_display_args
            logger.info(f"  Updated df_display_args with {len(current_pinned_rows)} pinned_rows")
            
            # Note: df_data_dict will be updated automatically when the executor
            # finishes and calls _on_progress_update. The frontend's useMemo for
            # extractPinnedRows depends on both summary_stats_data and pinned_rows,
            # so it will re-extract when either changes.
        
        # Trigger recomputation via executor
        # Use stored parameters from __init__
        file_path = self._file_path
        file_cache = self._file_cache
        
        # Get executor classes (use the same ones from __init__)
        sync_executor_class = self._sync_executor_class or _SyncExec
        parallel_executor_class = self._parallel_executor_class or _ParExec
        
        # Recompute summary stats with the new analysis
        # Note: progress_update_callback is already set on self._df, so we don't need to pass progress_listener
        # The progress_listener parameter is for ProgressNotification callbacks, while progress_update_callback
        # is for aggregated summary dictionaries
        # Pass current merged_sd as cached data, but remove the new analysis's stat keys so executor knows to compute them
        logger.info(f"  Triggering recomputation with new analysis {analysis_klass.__name__}")
        current_merged_sd = self._df.merged_sd.copy() if self._df.merged_sd else {}
        
        # Get the new analysis's expected stat keys from provides_defaults
        new_analysis_keys = set()
        if hasattr(analysis_klass, 'provides_defaults'):
            defaults = analysis_klass.provides_defaults
            if isinstance(defaults, dict):
                new_analysis_keys = set(defaults.keys())
        
        # Remove the new analysis's stat keys from cached data so executor knows they need to be computed
        if new_analysis_keys and current_merged_sd:
            cached_for_executor = {}
            for col_name, col_stats in current_merged_sd.items():
                if isinstance(col_stats, dict):
                    # Copy stats but remove keys from the new analysis
                    filtered_stats = {k: v for k, v in col_stats.items() if k not in new_analysis_keys}
                    cached_for_executor[col_name] = filtered_stats
                else:
                    cached_for_executor[col_name] = col_stats
        else:
            cached_for_executor = current_merged_sd
        
        self._df.auto_compute_summary(
            sync_executor_class,
            parallel_executor_class,
            file_cache=file_cache,
            progress_listener=None,  # progress_update_callback is already set and will be called automatically
            file_path=file_path,
            planning_function=self._planning_function,
            timeout_secs=self._timeout_secs,
            cached_merged_sd_override=cached_for_executor,  # Use filtered cached data so executor detects missing new stats
        )
