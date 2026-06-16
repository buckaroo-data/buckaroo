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
import weakref
from io import BytesIO
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from xorq.vendor.ibis.expr.types.relations import Table as XorqExpr
import pyarrow as pa
import pyarrow.parquet as pq
from traitlets import Unicode

from .buckaroo_widget import BuckarooInfiniteWidget, BuckarooWidget
from .customizations.styling import DefaultMainStyling, DefaultSummaryStatsStyling
from .customizations.xorq_autoclean_conf import NoCleaningConfXorq
from .customizations.xorq_stats_v2 import XORQ_STATS_V2
from .dataflow.autocleaning import PandasAutocleaning
from .dataflow.dataflow import CustomizableDataflow
from .dataflow.dataflow_extras import Sampling
from .df_util import old_col_new_col
from .pluggable_analysis_framework import perf_log
from .pluggable_analysis_framework.col_analysis import ColAnalysis
from .pluggable_analysis_framework.xorq_stat_pipeline import XorqDfStatsV2
from .serialization_utils import pd_to_obj, to_parquet

logger = logging.getLogger(__name__)


def _is_pandas(obj: Any) -> bool:
    return isinstance(obj, pd.DataFrame)


# Per-expression count cache. ibis Tables are immutable, so id(expr) ↔
# unique expression — same id, same .count() result. Saves ~250 ms on
# every repeated call against a large remote table (#795). Cache grows
# with one entry per unique expression object observed; entries become
# unreachable when the expression is GC'd, so for a long-running
# session it tracks the live set of expressions naturally.
_expr_count_cache: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _expr_count(expr_or_df: Any) -> int:
    if _is_pandas(expr_or_df):
        return len(expr_or_df)
    cached = _expr_count_cache.get(expr_or_df)
    if cached is not None:
        return cached
    try:
        result = int(expr_or_df.count().execute())
    except Exception:
        # Don't cache failures — a transient backend error would
        # otherwise poison the cache for the lifetime of this
        # expression object. Return 0 so callers don't break, log
        # so the failure is visible, leave the cache empty so the
        # next call retries the backend.
        logger.exception("_expr_count: backend count failed; not caching")
        return 0
    _expr_count_cache[expr_or_df] = result
    return result


class XorqSampling(Sampling):
    """Push-down sampling.

    Stats run against the full expression on the backend — there's no
    pre-stats pandas sample. For display, ``serialize_sample`` issues
    a *bounded* ``expr.limit(serialize_limit).execute()`` so the
    backend returns at most ``serialize_limit`` rows. A bare
    ``expr.execute()`` (no limit) is never emitted — that would pull
    the entire table and defeat the point of the push-down design.

    Pandas inputs (e.g. the error frame, or a postprocessor that
    materialised) are handled in-process: down-sampled if larger than
    ``serialize_limit``, otherwise returned as-is.
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
        if not cls.serialize_limit or cls.serialize_limit < 0:
            # Refuse to materialise an unbounded expr through display.
            # Subclasses that drive their own paginated loading
            # (e.g. ``XorqInfiniteSampling``) skip this path entirely
            # via ``skip_main_serial=True`` on the widget side.
            raise RuntimeError(
                f"{cls.__name__}.serialize_sample called on an ibis expression with "
                f"serialize_limit={cls.serialize_limit!r}; refusing to issue an "
                "unbounded expr.execute(). Use a positive serialize_limit, or skip "
                "the main serial on a widget that paginates.")
        return df_or_expr.limit(cls.serialize_limit).execute()


class XorqAutocleaning(PandasAutocleaning):
    """Autocleaning + interpreter for xorq/ibis expressions.

    Inherits the full ``PandasAutocleaning.handle_ops_and_clean`` pipeline
    (quick-ops → merge → run lisp interpreter → make_origs → code
    generation) unchanged. The xorq-flavoured piece is on the conf side:
    ``autocleaning_analysis_klasses`` is empty because the pandas-flavoured
    cleaning analyses (HeuristicFracs, etc.) don't work against ibis exprs,
    which keeps ``cleaning_sd`` empty for this conf today — so the base
    ``make_origs`` correctly short-circuits to ``cleaned_df`` without ever
    constructing a ``pd.DataFrame`` from columns.

    The interpreter itself runs unmodified: ``buckaroo_transform`` in
    ``jlisp.configure_utils`` routes anything that isn't pandas or polars
    through a pass-through copy, and each xorq Command's ``transform``
    returns a new expr.
    """


class XorqDataflow(CustomizableDataflow["XorqExpr"]):
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

    def _get_summary_sd(self, processed_df: "XorqExpr | pd.DataFrame"):
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
        cache_storage = getattr(self, 'cache_storage', None)
        with perf_log.perf_span("firstpull.summary_stats"):
            stats = self.DFStatsClass(
                processed_df, self.analysis_klasses, self.df_name,
                debug=self.debug, cache_storage=cache_storage,
                skip_columns=getattr(self, 'skip_stat_columns', None))
        sdf = stats.sdf
        if stats.errs:
            if self.debug:
                raise Exception("Error executing analysis")
            errs = stats.errs
        else:
            errs = {}
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


def window_to_parquet(processed_df, start, end, sort_col=None, ascending=True) -> bytes:
    """Materialise rows ``[start, end)`` and serialise to parquet — *no
    pandas detour for the ibis path*.

    Mirrors the polars infinite widget's wire path: arrow → parquet,
    not arrow → pandas → fastparquet. The bounded query
    ``expr.limit(end - start, offset=start)`` (after ``order_by`` when
    ``sort_col`` is set) goes straight to ``to_pyarrow()``; the
    resulting ``pyarrow.Table`` is column-renamed to buckaroo's
    rewritten ``a, b, c`` space, an ``index`` column with absolute
    offsets ``[start, start + n)`` is appended, and the table is
    written with ``pyarrow.parquet.write_table``.

    For a pandas DataFrame (postprocessor materialised, or
    error-frame fallback) we still go through the pandas
    ``to_parquet`` helper — there's no expression to push down.

    Shared by ``XorqBuckarooInfiniteWidget`` (Jupyter, sends via
    widget comm) and the standalone server's
    ``handle_infinite_request_xorq`` (WebSocket binary frame). Lifted
    to module level so both transports drive one push-down path.
    """
    with perf_log.perf_span("firstpull.window_to_parquet", start=start, end=end):
        return _window_to_parquet(processed_df, start, end, sort_col, ascending)


def _window_to_parquet(processed_df, start, end, sort_col, ascending) -> bytes:
    if _is_pandas(processed_df):
        if sort_col is not None:
            processed_df = processed_df.sort_values(by=[sort_col], ascending=ascending)
        df = processed_df[start:end].copy()
        df.index = pd.RangeIndex(start, start + len(df))
        return to_parquet(df)

    expr = processed_df
    if sort_col is not None:
        expr = expr.order_by(
            expr[sort_col].asc() if ascending else expr[sort_col].desc())
    # Rename original columns to the rewritten 'a, b, c' space the
    # frontend works in. Done at the expression level — and *before*
    # the limit — so the outermost op stays ``Limit`` (the bounded
    # plan stays observable for spies / query inspection).
    rename_select = [
        expr[orig].name(rew)
        for orig, rew in old_col_new_col(processed_df)]
    renamed = expr.select(rename_select)
    windowed = renamed.limit(end - start, offset=start)
    table = windowed.to_pyarrow()
    # Append absolute-offset index column for the frontend.
    index_arr = pa.array(
        list(range(start, start + len(table))), type=pa.int64())
    table = table.append_column('index', index_arr)
    out = BytesIO()
    pq.write_table(table, out, compression='none')
    return out.getvalue()


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

        # All slicing happens here so it's obvious that nothing executes
        # the full expression. Each request emits exactly one bounded
        # window query (``expr.limit(end - start, offset=start).to_pyarrow()``)
        # plus one aggregate (``expr.count().execute()`` for total length).
        try:
            total_length = _expr_count(processed_df)
            sort = new_payload_args.get('sort')
            sort_col = None
            ascending = True
            if sort:
                processed_sd = self.dataflow.widget_args_tuple[2]
                sort_col = processed_sd[sort]['orig_col_name']
                ascending = new_payload_args.get('sort_direction') == 'asc'

            window_bytes = window_to_parquet(processed_df, start, end, sort_col, ascending)
            self.send(
                {"type": "infinite_resp", 'key': new_payload_args,
                 'data': [], 'length': total_length},
                [window_bytes])

            # Sorted requests don't piggyback a second window today.
            if sort:
                return
            second_pa = new_payload_args.get('second_request')
            if not second_pa:
                return
            extra_start, extra_end = second_pa.get('start'), second_pa.get('end')
            extra_bytes = window_to_parquet(processed_df, extra_start, extra_end)
            self.send(
                {"type": "infinite_resp", 'key': second_pa,
                 'data': [], 'length': total_length},
                [extra_bytes])
        except Exception as e:
            logger.error(e)
            stack_trace = traceback.format_exc()
            self.send(
                {"type": "infinite_resp", 'key': new_payload_args,
                 'data': [], 'error_info': stack_trace, 'length': 0})
            raise
