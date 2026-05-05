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
import traceback
from typing import Any

import pandas as pd
from traitlets import Unicode

from .buckaroo_widget import BuckarooInfiniteWidget, BuckarooWidget
from .customizations.styling import DefaultMainStyling, DefaultSummaryStatsStyling
from .customizations.xorq_stats_v2 import XORQ_STATS_V2
from .dataflow.autocleaning import (
    AutocleaningConfig, PandasAutocleaning, generate_quick_ops, merge_ops, ops_eq)
from .dataflow.dataflow import CustomizableDataflow
from .dataflow.dataflow_extras import Sampling
from .df_util import old_col_new_col
from .jlisp.lisp_utils import s
from .pluggable_analysis_framework.col_analysis import ColAnalysis
from .pluggable_analysis_framework.xorq_stat_pipeline import XorqDfStatsV2
from .serialization_utils import pd_to_obj, to_parquet

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


def _xorq_search(expr, _col, val):
    """Filter rows where any string column contains ``val``.

    Mirrors the contract of the pandas / polars Search commands: an
    empty value short-circuits to a no-op so the frontend can clear
    the search by sending ``""``.
    """
    if val is None or val == "":
        return expr
    schema = expr.schema()
    string_cols = [name for name in expr.columns if schema[name].is_string()]
    if not string_cols:
        return expr
    cond = None
    for c in string_cols:
        c_cond = expr[c].contains(val)
        cond = c_cond if cond is None else cond | c_cond
    return expr.filter(cond)


class XorqSearch:
    """Search command for xorq exprs — symbol/pattern only.

    Defines the lisp symbol (``search``) and the quick-args pattern
    that the frontend uses for the search box. The actual filter is
    applied directly by ``XorqAutocleaning`` (see ``_XORQ_OP_HANDLERS``)
    rather than going through ``configure_buckaroo``'s pandas/polars
    interpreter, since ibis exprs are immutable and can't ``.copy()``.
    """

    command_default = [s('search'), s('df'), "col", ""]
    command_pattern = [[3, 'term', 'type', 'string']]
    quick_args_pattern = [[3, 'term', 'type', 'string']]

    @staticmethod
    def transform(expr, col, val):
        return _xorq_search(expr, col, val)

    @staticmethod
    def transform_to_py(expr, col, val):
        return f"    expr = expr.filter(... contains('{val}'))"


_XORQ_OP_HANDLERS = {'search': _xorq_search}


class NoCleaningConfXorq(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [XorqSearch]
    quick_command_klasses = [XorqSearch]
    name = ""


class XorqAutocleaning(PandasAutocleaning):
    """Cleaning is skipped for ibis exprs (the lisp interpreter targets
    pandas), but quick commands like Search are applied directly.

    Each quick op is dispatched through ``_XORQ_OP_HANDLERS`` —
    expression-to-expression transforms — so the result is still a
    pushed-down xorq expr that downstream stats and pagination consume
    unchanged.
    """

    def handle_ops_and_clean(self, df, cleaning_method, quick_command_args, existing_operations):
        if df is None:
            return None
        quick_ops = generate_quick_ops(self.quick_command_klasses, quick_command_args)
        if ops_eq(existing_operations, [{'meta': 'no-op'}]):
            existing_for_merge = []
        else:
            existing_for_merge = existing_operations
        final_ops = merge_ops(existing_for_merge, quick_ops)
        if not final_ops:
            return [df, {}, "", []]
        result = self._apply_xorq_ops(df, final_ops)
        return [result, {}, "", final_ops]

    @staticmethod
    def _apply_xorq_ops(expr, ops):
        for op in ops:
            sym_name = op[0]['symbol'] if isinstance(op[0], dict) else op[0]
            handler = _XORQ_OP_HANDLERS.get(sym_name)
            if handler is None:
                continue
            handler_args = op[2:]
            expr = handler(expr, *handler_args)
        return expr


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


class XorqInfiniteSampling(XorqSampling):
    """Pagination drives data loading; no display-time sampling."""
    serialize_limit = -1


class XorqBuckarooInfiniteWidget(XorqBuckarooWidget, BuckarooInfiniteWidget):
    """Infinite-scroll buckaroo over an ibis/xorq expression.

    Each grid window fires an ``infinite_request`` carrying ``start`` /
    ``end`` (and optionally a ``sort`` column). The widget responds with
    a parquet slice obtained via
    ``expr.limit(end - start, offset=start).execute()`` — sorted on the
    backend when the request includes a sort, plain LIMIT/OFFSET
    otherwise. The total row count is one ``expr.count().execute()``
    per request.

    For a postprocessor that materialises to pandas (or the error-frame
    fallback), the slice falls back to plain pandas indexing.
    """

    render_func_name = Unicode("BuckarooInfiniteWidget").tag(sync=True)
    sampling_klass = XorqInfiniteSampling

    def _handle_payload_args(self, new_payload_args):
        start, end = new_payload_args['start'], new_payload_args['end']
        _unused, processed_df, merged_sd = self.dataflow.widget_args_tuple
        if processed_df is None:
            return

        try:
            total_length = _expr_count(processed_df)
            sort = new_payload_args.get('sort')
            if sort:
                sort_dir = new_payload_args.get('sort_direction')
                processed_sd = self.dataflow.widget_args_tuple[2]
                orig_col = processed_sd[sort]['orig_col_name']
                slice_df = self._sliced_pandas(
                    processed_df, start, end, sort_col=orig_col, ascending=(sort_dir == 'asc'))
                self.send(
                    {"type": "infinite_resp", 'key': new_payload_args,
                     'data': [], 'length': total_length},
                    [to_parquet(slice_df)])
                return

            slice_df = self._sliced_pandas(processed_df, start, end)
            self.send(
                {"type": "infinite_resp", 'key': new_payload_args,
                 'data': [], 'length': total_length},
                [to_parquet(slice_df)])

            second_pa = new_payload_args.get('second_request')
            if not second_pa:
                return
            extra_start, extra_end = second_pa.get('start'), second_pa.get('end')
            extra_df = self._sliced_pandas(processed_df, extra_start, extra_end)
            self.send(
                {"type": "infinite_resp", 'key': second_pa,
                 'data': [], 'length': total_length},
                [to_parquet(extra_df)])
        except Exception as e:
            logger.error(e)
            stack_trace = traceback.format_exc()
            self.send(
                {"type": "infinite_resp", 'key': new_payload_args,
                 'data': [], 'error_info': stack_trace, 'length': 0})
            raise

    @staticmethod
    def _sliced_pandas(processed_df, start, end, sort_col=None, ascending=True):
        """Materialise rows ``[start, end)`` as a pandas DataFrame.

        For an ibis expr we push ``order_by + limit/offset`` to the
        backend. For a pandas frame (postprocessor materialised, or
        error-frame fallback) we slice in-process.

        The pandas index on the returned frame is set to
        ``RangeIndex(start, start + len(df))`` so ``to_parquet`` (which
        injects ``index`` from ``df.index``) gives the frontend the
        correct absolute row numbers.
        """
        if _is_pandas(processed_df):
            if sort_col is not None:
                processed_df = processed_df.sort_values(by=[sort_col], ascending=ascending)
            df = processed_df[start:end].copy()
            df.index = pd.RangeIndex(start, start + len(df))
            return df

        expr = processed_df
        if sort_col is not None:
            order = expr[sort_col].asc() if ascending else expr[sort_col].desc()
            expr = expr.order_by(order)
        df = expr.limit(end - start, offset=start).execute()
        df.index = pd.RangeIndex(start, start + len(df))
        return df
