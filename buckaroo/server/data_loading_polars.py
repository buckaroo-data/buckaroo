"""Polars counterparts of the pandas-based loaders in ``data_loading``.

Lives in its own module so polars stays an optional dependency — the
server only imports this when ``/load`` is called with
``backend: "polars"``. Mirrors the shape of ``data_loading``:

* :func:`load_file_polars` reads parquet/csv/tsv/json eagerly into a
  ``pl.DataFrame``; :func:`load_file_polars_lazy` opens the same files
  as a ``pl.LazyFrame`` (``polars_mode: "lazy"``, the default, #993) so
  a session never holds the whole table.
* :class:`PolarsServerDataflow` is the polars analogue of
  ``ServerDataflow`` — same role in the pipeline, polars-flavored
  analysis / autocleaning / stats / sampling classes (lifted from
  ``PolarsBuckarooInfiniteWidget``). :class:`PolarsLazyServerDataflow`
  carries a LazyFrame through the same pipeline, with its stats computed
  by :class:`PlLazyDfStatsV2` as one streaming select over the scan.
* :func:`handle_infinite_request_buckaroo_polars` is the polars
  equivalent of ``handle_infinite_request_buckaroo`` — applies the
  live ``search_string`` as a literal substring match on String
  columns (mirrors ``search_df_str`` semantics from the pandas path
  so the client-facing behaviour is identical). Over a LazyFrame it
  collects only the requested window.
"""
import os
import traceback
from typing import Any, List, Mapping, Tuple
from io import BytesIO

import polars as pl

from buckaroo.dataflow.dataflow import CustomizableDataflow
from buckaroo.dataflow.styling_core import InitSD
from buckaroo.dataflow.autocleaning import PandasAutocleaning
from buckaroo.customizations.pl_autocleaning_conf import NoCleaningConfPl
from buckaroo.customizations import pl_lazy_stats
from buckaroo.customizations.pl_lazy_stats import (
    LAZY_SEED_KEYS, PL_ANALYSIS_LAZY, LazyStatPipeline, collect_lazy_stats, lazy_row_count)
from buckaroo.customizations.styling import DefaultSummaryStatsStyling
from buckaroo.df_util import to_chars
from buckaroo.pluggable_analysis_framework.col_analysis import SDType
from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
from buckaroo.pluggable_analysis_framework.safe_summary_df import output_full_reproduce
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline, errors_to_errdict
from buckaroo.polars_buckaroo import (
    PLSampling, PolarsMainStyling, local_analysis_klasses, prepare_df_for_serialization)
from buckaroo.serialization_utils import pd_to_obj, make_infinite_resp


class PolarsServerSampling(PLSampling):
    """Server-mode polars sampling. Inherits ``PLSampling``'s widget
    defaults but caps pre-stats work at ``pre_limit`` so a multi-million-row
    /load doesn't OOM the stats pipeline."""
    pre_limit = 1_000_000
    serialize_limit = -1  # infinite mode — no per-page sample cap


class PolarsServerDataflow(CustomizableDataflow[pl.DataFrame]):
    """Headless polars dataflow matching ``PolarsBuckarooInfiniteWidget``."""
    analysis_klasses = local_analysis_klasses
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = tuple([NoCleaningConfPl])
    DFStatsClass = PlDfStatsV2
    sampling_klass = PolarsServerSampling

    def _df_to_obj(self, df):
        # Matches PolarsBuckarooWidget._df_to_obj — pandas frames pass
        # straight through, polars frames go via to_pandas for the JSON
        # initial-state path. (The hot path is the parquet infinite handler
        # below, not this; this is only the initial empty/seed payload.)
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            return pd_to_obj(self.sampling_klass.serialize_sample(df))
        return pd_to_obj(self.sampling_klass.serialize_sample(df.to_pandas()))


class PolarsLazySampling(PLSampling):
    """No pre-stats sample and no main serial: the stats are one select
    over the scan and the grid is paged by the infinite handler."""
    pre_limit = False
    serialize_limit = -1

    @classmethod
    def pre_stats_sample(cls, lf, /):
        return lf

    @classmethod
    def serialize_sample(cls, lf, /):
        raise RuntimeError(
            "PolarsLazySampling.serialize_sample would collect the whole scan; "
            "lazy sessions page rows through the infinite handler (skip_main_serial).")


class PlLazyDfStatsV2:
    """Summary-stats executor for a LazyFrame (#993).

    Everything that needs the data is one lazy select over the scan, or
    over a sample of it past ``LAZY_STATS_SAMPLE_ROWS`` rows
    (``collect_lazy_stats``), collected with the streaming engine. Its
    scalars seed ``StatPipeline.process_column`` as ``initial_stats``,
    so the derived @stat functions and the structural styling classes
    run unchanged. Stat functions that need a raw series are dropped —
    there is no series to hand out without collecting the column.
    """
    engine = "streaming"

    @classmethod
    def verify_analysis_objects(cls, objs):
        LazyStatPipeline(objs)

    def __init__(self, lf: pl.LazyFrame, col_analysis_objs, operating_df_name=None, debug=False,
            skip_columns=None):
        self.df = lf
        full = LazyStatPipeline(col_analysis_objs, unit_test=False)
        self.ap = LazyStatPipeline([sf for sf in full.all_stat_funcs if not sf.needs_raw], unit_test=False)
        stats_by_col = collect_lazy_stats(lf, engine=self.engine)
        skip = set(skip_columns or ())
        self.sdf: SDType = {}
        errors: List[Any] = []
        for i, (orig_col, dtype) in enumerate(lf.collect_schema().items()):
            rewritten = to_chars(i)
            if orig_col in skip or rewritten in skip:
                self.sdf[rewritten] = {'orig_col_name': orig_col, 'rewritten_col_name': rewritten}
                continue
            col_result, col_errors = self.ap.process_column(rewritten, dtype,
                initial_stats={'orig_col_name': orig_col, 'rewritten_col_name': rewritten, **stats_by_col[orig_col]})
            self.sdf[rewritten] = col_result
            errors.extend(col_errors)
        self.errs = errors_to_errdict(errors)
        self.stat_errors = []
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def add_analysis(self, a_obj):
        raise NotImplementedError("a lazy polars session's analysis classes are fixed at load time")


LAZY_ANALYSIS_KLASSES = list(PL_ANALYSIS_LAZY) + [DefaultSummaryStatsStyling, PolarsMainStyling]

# Stat keys the eager polars pipeline provides that a lazy session doesn't;
# reported in df_meta so a client can tell which pinned rows will be blank.
LAZY_STATS_OMITTED = sorted(
    StatPipeline(local_analysis_klasses, unit_test=False).provided_summary_facts_set
    - LazyStatPipeline(LAZY_ANALYSIS_KLASSES, unit_test=False).provided_summary_facts_set
    - LAZY_SEED_KEYS)


# ``Any`` rather than ``pl.LazyFrame``: DataFrameT is bound to the eager
# ``DataFrameLike`` contract (``len`` / row-slice), which a LazyFrame can't
# meet. Every site of the shared body that would call those is overridden
# here (sampling, populate_df_meta) or skipped (skip_main_serial).
class PolarsLazyServerDataflow(CustomizableDataflow[Any]):
    """Headless dataflow over a polars LazyFrame (#993).

    Same pipeline as :class:`PolarsServerDataflow`, but the frame is never
    collected: stats are one streaming select (``PlLazyDfStatsV2``), the
    row count is ``select(pl.len())``, and the main grid is paged by the
    infinite handler. Autocleaning and post-processing aren't offered.
    """
    analysis_klasses = LAZY_ANALYSIS_KLASSES
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = tuple([NoCleaningConfPl])
    DFStatsClass = PlLazyDfStatsV2
    sampling_klass = PolarsLazySampling

    def __init__(self, *args, **kwargs):
        # keyed by frame identity; the frame is kept so an id can't be reused
        self._row_counts: dict = {}
        super().__init__(*args, **kwargs)

    def _row_count(self, lf: pl.LazyFrame) -> int:
        key = id(lf)
        if key not in self._row_counts:
            self._row_counts[key] = (lf, lazy_row_count(lf))
        return self._row_counts[key][1]

    def populate_df_meta(self) -> None:
        if self.processed_df is None:
            self.df_meta = {'columns': 0, 'filtered_rows': 0, 'rows_shown': 0, 'total_rows': 0}
            return
        rows = self._row_count(self.processed_df)
        total = self._row_count(self.orig_df)
        self.df_meta = {'columns': len(self.processed_df.collect_schema()), 'filtered_rows': rows,
            'rows_shown': rows, 'total_rows': total, 'stats_omitted': LAZY_STATS_OMITTED,
            'stats_sampled': total > pl_lazy_stats.LAZY_STATS_SAMPLE_ROWS}


def load_file_polars(path: str) -> pl.DataFrame:
    """Eager polars read. Extension dispatch mirrors :func:`load_file`.

    ``.json`` uses ``pl.read_json`` (standard JSON array of records) to
    match ``pd.read_json``'s default ``lines=False`` — same file must
    load under either backend. Newline-delimited JSON is reachable via
    the explicit ``.ndjson`` extension.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pl.read_csv(path)
    elif ext == ".tsv":
        return pl.read_csv(path, separator="\t")
    elif ext in (".parquet", ".parq"):
        return pl.read_parquet(path)
    elif ext == ".json":
        return pl.read_json(path)
    elif ext == ".ndjson":
        return pl.read_ndjson(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def load_file_polars_lazy(path: str) -> pl.LazyFrame:
    """Open the file as a ``pl.LazyFrame``; nothing is read until a
    collect. A ``.json`` array has no scan, so it is read eagerly and
    wrapped — that one case still holds the frame. A missing file
    surfaces as ``FileNotFoundError`` on the first schema resolution."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pl.scan_csv(path)
    elif ext == ".tsv":
        return pl.scan_csv(path, separator="\t")
    elif ext in (".parquet", ".parq"):
        return pl.scan_parquet(path)
    elif ext == ".json":
        return pl.read_json(path).lazy()
    elif ext == ".ndjson":
        return pl.scan_ndjson(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def get_metadata_polars(df: "pl.DataFrame | pl.LazyFrame", path: str) -> dict:
    if isinstance(df, pl.LazyFrame):
        schema = df.collect_schema()
        columns = [{"name": str(c), "dtype": str(d)} for c, d in schema.items()]
        return {"path": path, "rows": lazy_row_count(df), "columns": columns}
    columns = [{"name": str(c), "dtype": str(d)} for c, d in zip(df.columns, df.dtypes)]
    return {"path": path, "rows": len(df), "columns": columns}


def create_polars_dataflow(df, column_config_overrides=None, extra_grid_config=None,
        init_sd: InitSD | None = None) -> "PolarsServerDataflow | PolarsLazyServerDataflow":
    klass = PolarsLazyServerDataflow if isinstance(df, pl.LazyFrame) else PolarsServerDataflow
    return klass(df, column_config_overrides=column_config_overrides,
        extra_grid_config=extra_grid_config, init_sd=init_sd, skip_main_serial=True)


def _search_mask(string_cols: List[str], search_string: str) -> pl.Expr:
    # Literal (``literal=True``) so user typing isn't treated as regex;
    # this matches the pandas server path's ``search_df_str`` semantics.
    return pl.any_horizontal(pl.col(c).str.contains(search_string, literal=True) for c in string_cols)


def _eager_window(processed_df: pl.DataFrame, merged_sd, payload_args: dict,
        search_string: str) -> Tuple[int, pl.DataFrame]:
    from buckaroo.server.window import clamp_window

    if search_string:
        string_cols = [c for c, dt in zip(processed_df.columns, processed_df.dtypes) if dt == pl.String]
        if string_cols:
            filtered_df = processed_df.filter(_search_mask(string_cols, search_string))
        else:
            # No string columns to search → no matches. ``search_df_str``
            # starts from an all-False mask and only ORs over string/object
            # columns, so a non-empty search on a numeric-only frame
            # produces an empty result. Matching that here keeps the UI
            # honest: a search term should never silently appear unfiltered.
            filtered_df = processed_df.clear()
    else:
        filtered_df = processed_df

    start, end = clamp_window(payload_args.get("start"), payload_args.get("end"), len(filtered_df))

    sort = payload_args.get("sort")
    if sort:
        ascending = payload_args.get("sort_direction") == "asc"
        converted_sort_column = merged_sd[sort]["orig_col_name"]
        sorted_df = filtered_df.with_row_index().sort(converted_sort_column, descending=not ascending)
        return len(filtered_df), sorted_df[start:end]
    return len(filtered_df), filtered_df.with_row_index()[start:end]


def _lazy_window(processed_df: pl.LazyFrame, merged_sd, payload_args: dict, search_string: str,
        total_rows: int) -> Tuple[int, pl.DataFrame]:
    """Same window semantics as :func:`_eager_window`, collecting only the
    window. An unfiltered request reuses the dataflow's row count; a
    search costs a count pass and a window pass over the scan."""
    from buckaroo.server.window import clamp_window

    if search_string:
        string_cols = [c for c, dt in processed_df.collect_schema().items() if dt == pl.String]
        filtered = processed_df.filter(_search_mask(string_cols, search_string)) if string_cols else processed_df.clear()
        n_rows = lazy_row_count(filtered)
    else:
        filtered, n_rows = processed_df, total_rows

    start, end = clamp_window(payload_args.get("start"), payload_args.get("end"), n_rows)

    sort = payload_args.get("sort")
    if sort:
        ascending = payload_args.get("sort_direction") == "asc"
        converted_sort_column = merged_sd[sort]["orig_col_name"]
        return n_rows, _sorted_window(filtered, converted_sort_column, not ascending, start, end)
    window = filtered.slice(start, end - start).with_row_index(offset=start)
    return n_rows, window.collect(engine="streaming")


def _sorted_window(filtered: pl.LazyFrame, sort_col: str, descending: bool, start: int, end: int) -> pl.DataFrame:
    """Rows ``start:end`` of ``filtered`` sorted by ``sort_col``, each with
    its row index in ``filtered`` (as the eager path does).

    polars does not turn sort + slice into a bounded top-k, and sorting the
    whole frame holds every column. So the sort runs over the row index and
    the sort column alone, then a second streamed pass picks the window's
    rows by index. Peak memory follows the sort column and the index rather
    than the whole table; it is not constant, because polars' streaming
    reader still reads ahead in proportion to the scan."""
    idx = "index"
    keyed = filtered.with_row_index(idx)
    order = keyed.select(idx, sort_col).sort(sort_col, descending=descending).slice(start, end - start).select(
        idx).collect(engine="streaming")
    rows = keyed.filter(pl.col(idx).is_in(order[idx].implode())).collect(engine="streaming")
    # a left join keeps the left (sorted) order
    return order.join(rows, on=idx, how="left", maintain_order="left")


def handle_infinite_request_buckaroo_polars(
    dataflow: "PolarsServerDataflow | PolarsLazyServerDataflow", payload_args: dict, search_string: str = ""
) -> tuple[Mapping[str, Any], bytes]:
    """Polars analogue of :func:`handle_infinite_request_buckaroo`.

    ``search_string`` is the live-typed filter (#838) — applied as a
    literal substring match across all polars ``String`` columns.
    """
    _unused, processed_df, merged_sd = dataflow.widget_args_tuple
    if processed_df is None:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0}, b"")
    try:
        if isinstance(processed_df, pl.LazyFrame):
            total_rows = (dataflow.df_meta or {}).get("filtered_rows")
            if total_rows is None:
                total_rows = lazy_row_count(processed_df)
            n_rows, slice_df = _lazy_window(processed_df, merged_sd, payload_args, search_string, total_rows)
        else:
            n_rows, slice_df = _eager_window(processed_df, merged_sd, payload_args, search_string)

        out = BytesIO()
        prepare_df_for_serialization(slice_df).write_parquet(out, compression="uncompressed")
        # Native polars parquet — strings are not JSON-wrapped.
        return make_infinite_resp(payload_args, n_rows, out.getvalue(), json_columns=[])
    except Exception:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0,
            "error_info": traceback.format_exc()}, b"")
