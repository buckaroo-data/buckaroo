"""XorqBuckarooWidget — buckaroo against a xorq/ibis expression.

Stats compile to a single batched ``expr.aggregate(...)`` query plus
per-column histogram queries; the only thing pulled into Python is a
display-sized sample (via ``expr.limit(N).execute()``). Postprocessing
is expression-to-expression: registered functions take the underlying
xorq expr and return a new expr (or pandas DataFrame).

Optional dependency: ``pip install 'buckaroo[xorq]'``.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .buckaroo_widget import BuckarooWidget
from .customizations.styling import DefaultMainStyling, DefaultSummaryStatsStyling
from .customizations.xorq_stats_v2 import XORQ_STATS_V2
from .dataflow.autocleaning import AutocleaningConfig, PandasAutocleaning
from .dataflow.dataflow import CustomizableDataflow
from .dataflow.dataflow_extras import Sampling
from .df_util import old_col_new_col
from .pluggable_analysis_framework.col_analysis import ColAnalysis
from .pluggable_analysis_framework.xorq_stat_pipeline import XorqDfStatsV2
from .serialization_utils import pd_to_obj

logger = logging.getLogger(__name__)


def _is_pandas(obj: Any) -> bool:
    return isinstance(obj, pd.DataFrame)


def _expr_count(expr_or_df: Any) -> int:
    if _is_pandas(expr_or_df):
        return len(expr_or_df)
    try:
        return int(expr_or_df.count().execute())
    except Exception:
        return 0


class XorqSampling(Sampling):
    """Push-down sampling.

    Stats run against the full expression on the backend — there's no
    pre-stats pandas sample. For display, ``serialize_sample`` materialises
    ``expr.limit(serialize_limit).execute()`` (or returns a pandas
    DataFrame as-is, e.g. an error frame from the post-processing path).
    """

    pre_limit = False

    @classmethod
    def pre_stats_sample(cls, expr):
        return expr

    @classmethod
    def serialize_sample(cls, df_or_expr):
        if _is_pandas(df_or_expr):
            if cls.serialize_limit and len(df_or_expr) > cls.serialize_limit:
                return df_or_expr.sample(cls.serialize_limit).sort_index()
            return df_or_expr
        if cls.serialize_limit:
            return df_or_expr.limit(cls.serialize_limit).execute()
        return df_or_expr.execute()


class NoCleaningConfXorq(AutocleaningConfig):
    """No-cleaning config local to the xorq path — avoids importing
    ``NoCleaningConfPl`` (which would transitively load polars and break
    a polars-less ``buckaroo[xorq]`` install)."""

    autocleaning_analysis_klasses = []
    command_klasses = []
    quick_command_klasses = []
    name = ""


class XorqAutocleaning(PandasAutocleaning):
    """Pass-through autocleaning.

    Cleaning operations run a lisp interpreter over a pandas DataFrame —
    that surface doesn't apply to ibis exprs. Skip cleaning entirely so
    the expr flows through to ``_compute_processed_result`` unchanged.
    """

    def handle_ops_and_clean(self, df, cleaning_method, quick_command_args, existing_operations):
        if df is None:
            return None
        return [df, {}, "", []]


class XorqDataflow(CustomizableDataflow):
    """Dataflow specialised for ibis/xorq expression inputs.

    Two pieces of behaviour differ from the pandas dataflow:

    1. ``populate_df_meta`` can't ``len(expr)`` — it issues an
       ``expr.count().execute()`` for the row count.
    2. ``_get_summary_sd`` re-keys the summary dict from original column
       names (what ``XorqStatPipeline`` produces) to the rewritten
       ``a, b, c`` names that ``pd_to_obj`` and the styling layer expect.
    """

    def populate_df_meta(self) -> None:
        if self.processed_df is None:
            self.df_meta = {
                'columns': 0, 'filtered_rows': 0,
                'rows_shown': 0, 'total_rows': 0}
            return
        rows = _expr_count(self.processed_df)
        limit = self.sampling_klass.serialize_limit
        rows_shown = min(rows, limit) if limit else rows
        self.df_meta = {
            'columns': len(self.processed_df.columns),
            'filtered_rows': rows,
            'rows_shown': rows_shown,
            'total_rows': _expr_count(self.orig_df)}

    def _get_summary_sd(self, processed_df):
        if _is_pandas(processed_df):
            # The error path (and any postprocessor that returns a pandas
            # DataFrame) doesn't go through XorqStatPipeline. Return a
            # minimal SD so the main grid still renders.
            empty: dict = {}
            for orig_col, rewritten_col in old_col_new_col(processed_df):
                empty[rewritten_col] = {
                    'orig_col_name': orig_col,
                    'rewritten_col_name': rewritten_col}
            return empty, {}
        sdf, errs = super()._get_summary_sd(processed_df)
        rewritten = {}
        for orig_col, rewritten_col in old_col_new_col(processed_df):
            col_meta = dict(sdf.get(orig_col, {}))
            col_meta['orig_col_name'] = orig_col
            col_meta['rewritten_col_name'] = rewritten_col
            rewritten[rewritten_col] = col_meta
        return rewritten, errs


_XORQ_ANALYSIS_KLASSES = list(XORQ_STATS_V2) + [DefaultSummaryStatsStyling, DefaultMainStyling]


class XorqBuckarooWidget(BuckarooWidget):
    """Buckaroo widget over a xorq/ibis expression.

    Usage::

        import xorq.api as xo
        from buckaroo.xorq_buckaroo import XorqBuckarooWidget

        expr = xo.memtable({'price': [...], 'qty': [...]})
        XorqBuckarooWidget(expr)

    Postprocessing functions take and return a xorq expression::

        def top_categories(expr):
            return expr.filter(expr.qty > 1)

        widget = XorqBuckarooWidget(expr)
        widget.add_processing(top_categories)  # also selects it
    """

    analysis_klasses = _XORQ_ANALYSIS_KLASSES
    autocleaning_klass = XorqAutocleaning
    autoclean_conf = tuple([NoCleaningConfXorq])
    DFStatsClass = XorqDfStatsV2
    sampling_klass = XorqSampling
    dataflow_klass = XorqDataflow

    def _df_to_obj(self, df):
        return pd_to_obj(self.sampling_klass.serialize_sample(df))

    def _build_error_dataframe(self, e):
        return pd.DataFrame({'err': [str(e)]})

    def add_processing(self, expr_processing_func):
        """Register a postprocessing function and switch to it.

        ``expr_processing_func`` takes the current expression and returns
        either a new expression or a pandas DataFrame. The returned object
        replaces ``processed_df`` for display and stats; if it's still an
        expression, stats continue to push down.
        """
        proc_func_name = expr_processing_func.__name__

        class DecoratedXorqProcessing(ColAnalysis):
            provides_defaults = {}

            @classmethod
            def post_process_df(kls, expr):
                return [expr_processing_func(expr), {}]

            post_processing_method = proc_func_name

        DecoratedXorqProcessing.__name__ = f"DecoratedXorqProcessing_{proc_func_name}"
        self.add_analysis(DecoratedXorqProcessing)
        temp_state = self.buckaroo_state.copy()
        temp_state['post_processing'] = proc_func_name
        self.buckaroo_state = temp_state
