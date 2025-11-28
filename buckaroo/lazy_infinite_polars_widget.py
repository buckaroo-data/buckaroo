#!/usr/bin/env python
# coding: utf-8
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type
from io import BytesIO
from pathlib import Path

import anywidget
import polars as pl
import logging
from traitlets import Dict as TDict, Unicode, observe

from .dataflow.column_executor_dataflow import ColumnExecutorDataflow
from .customizations.polars_analysis import PL_Analysis_Klasses, ComputedDefaultSummaryStats, NOT_STRUCTS
from buckaroo.pluggable_analysis_framework.utils import json_postfix
from .pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from .df_util import old_col_new_col
from .serialization_utils import pd_to_obj
from .customizations.polars_analysis import HistogramAnalysis as _H
from buckaroo.file_cache.base import Executor as _SyncExec  # type: ignore            
#from buckaroo.file_cache.threaded_executor import ThreadedExecutor as _ParExec  # type: ignore
from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor as _ParExec
from buckaroo.file_cache.base import FileCache as _FC  # type: ignore

import polars.selectors as cs
from polars import functions as F


logger = logging.getLogger("buckaroo.widget")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[buckaroo] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

class SimpleAnalysis(PolarsAnalysis):


    provides_defaults = {'length':2, 'null_count':3, 'unique_count':5, 'empty_count':8}
    select_clauses = [
        (NOT_STRUCTS.len() - NOT_STRUCTS.is_duplicated().sum()).name.map(json_postfix('unique_count')),
        F.all().len().name.map(json_postfix('length')),
        F.col(pl.Utf8).str.count_matches("^$").sum().name.map(json_postfix('empty_count')),
        F.all().null_count().name.map(json_postfix('null_count'))]
    

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

    def __init__(
        self,
        ldf: pl.LazyFrame,
        *,
        analysis_klasses: Optional[List[Type[PolarsAnalysis]]] = None,
        debug: bool = False,
        column_executor_class: Optional[type] = None,
        file_path: Optional[str] = None,
        file_cache: Optional["FileCache"] = None,
        sync_executor_class: Optional[type] = None,
        #don't need parallel_executor_class  
        parallel_executor_class: Optional[type] = None,
    ) -> None:
        super().__init__()
        self._debug = debug
        self._ldf = ldf
        #default_analyses = PL_Analysis_Klasses
        default_analyses = [SimpleAnalysis]

        self._analyses = list(analysis_klasses) if analysis_klasses is not None else default_analyses

        # Build stable rewrites
        all_cols = self._ldf.collect_schema().names()
        empty_pl_df = pl.DataFrame({c: [] for c in all_cols})
        self._orig_to_rw = dict(old_col_new_col(empty_pl_df))
        self._rw_to_orig = {v: k for k, v in self._orig_to_rw.items()}

        # Optional cache short-circuit
        cached_merged_sd = None
        if file_path:
            md = file_cache.get_file_metadata(Path(file_path))  # type: ignore[arg-type]
            if md and 'merged_sd' in md:
                cached_merged_sd = md['merged_sd']

        # First-pass meta from polars directly (avoid constructing dataflow solely for meta)
        try:
            total_rows = int(ldf.select(pl.len().alias("__len")).collect().item())
        except Exception:
            total_rows = 0
        num_cols = len(all_cols)

        # Dataflow for summary stats with chosen executor
        self._df = ColumnExecutorDataflow(
            ldf,
            analysis_klasses=self._analyses,
            column_executor_class=column_executor_class)
        self.df_meta = {'columns': num_cols, 'rows_shown': 0, 'filtered_rows': 0, 'total_rows': total_rows}

        # Stream progress updates into df_data_dict so the UI reflects new stats as they arrive.
        def _on_progress_update(aggregated_summary: Dict[str, Dict[str, Any]]) -> None:
            try:
                rows = self._summary_to_rows(aggregated_summary or {})
                logger.info(
                    "Progress rows update: all_stats len=%s sample=%s",
                    len(rows),
                    (rows[0] if rows else None),
                )
                self.df_data_dict = {'main': [], 'all_stats': rows, 'empty': []}
            except Exception:
                logger.exception("error updating df_data_dict from progress")
        self._df.progress_update_callback = _on_progress_update

        # Prepare initial defaults so pinned rows have placeholders immediately
        def _initial_summary_defaults() -> Dict[str, Dict[str, Any]]:
            base: Dict[str, Dict[str, Any]] = {}
            for orig in all_cols:
                rw = self._orig_to_rw.get(orig, orig)
                entry: Dict[str, Any] = {
                    'orig_col_name': orig,
                    'rewritten_col_name': rw,
                }
                for ak in self._analyses:
                    try:
                        defaults = getattr(ak, 'provides_defaults', {}) or {}
                        if isinstance(defaults, dict):
                            entry.update(defaults)
                    except Exception:
                        continue
                base[rw] = entry
            return base
        _initial_sd = _initial_summary_defaults()
        # Compute summary stats and wire progress to a trait
        def _listener(note):
            # Minimal progress surface; expand as needed

            logger.info(
                "ProgressNotification for %s  status %s message %s",
                note.col_group, note.success, note.failure_message)

            self.executor_progress = {
                'success': note.success,
                'col_group': note.col_group,
                'message': note.failure_message or ''
            }

        # Compute summary (cache → auto-select via dataflow using executor log)
        if cached_merged_sd is not None:
            summary_sd = cached_merged_sd
        else:
            chosen_sync_exec = sync_executor_class or _SyncExec
            chosen_par_exec = parallel_executor_class or _ParExec
            self._df.auto_compute_summary(
                chosen_sync_exec,
                chosen_par_exec,
                progress_listener=_listener,
            )
            # Important: DFViewer renders pinned-top rows by extracting values from
            # summary_stats_data using the configured pinned_rows (e.g., "unique_count",
            # "null_count"). If summary_stats_data is empty at first render (timeouts or
            # background execution), AG‑Grid has nothing to pin and the pinned area will
            # not appear. We seed summary_sd with _initial_sd (built from provides_defaults)
            # so all_stats has placeholders immediately and the pinned rows render even
            # before the background computation completes.
            summary_sd = self._df.merged_sd or _initial_sd
        summary_rows = self._summary_to_rows(summary_sd)
        logger.info(
            "Initial all_stats prepared: len=%s sample=%s",
            len(summary_rows),
            (summary_rows[0] if summary_rows else None),
        )

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
                {'primary_key_val': 'unique_count',     'displayer_args': {'displayer': 'obj' } },
                {'primary_key_val': 'null_count',     'displayer_args': {'displayer': 'obj' } },
                {'primary_key_val': 'empty_count',     'displayer_args': {'displayer': 'obj' } },
            ],
            "column_config": initial_col_config,
            "left_col_configs": [{"col_name": "index", "header_name": "index", "displayer_args": {"displayer": "obj"}}],
        }
        logger.info("LazyInfinite init: total_rows=%s; initial columns=%s", total_rows, [c.get("header_name") for c in initial_col_config])
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
        import pandas as pd
        if not summary:
            return []
        df = pd.DataFrame(summary)
        return pd_to_obj(df)

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
            import traceback
            stack_trace = traceback.format_exc()
            self.send({"type": "infinite_resp", 'key': new_payload_args, 'data': [], 'error_info': stack_trace, 'length': 0}, [])
            logger.exception("error handling payload args: %s", e)


