"""Polars counterparts of the pandas-based loaders in ``data_loading``.

Lives in its own module so polars stays an optional dependency — the
server only imports this when ``/load`` is called with
``backend: "polars"``. Mirrors the shape of ``data_loading``:

* :func:`load_file_polars` reads parquet/csv/tsv/json eagerly into a
  ``pl.DataFrame``.
* :class:`PolarsServerDataflow` is the polars analogue of
  ``ServerDataflow`` — same role in the pipeline, polars-flavored
  analysis / autocleaning / stats / sampling classes (lifted from
  ``PolarsBuckarooInfiniteWidget``).
* :func:`handle_infinite_request_buckaroo_polars` is the polars
  equivalent of ``handle_infinite_request_buckaroo`` — applies the
  live ``search_string`` as a literal substring match on String
  columns (mirrors ``search_df_str`` semantics from the pandas path
  so the client-facing behaviour is identical).
* :class:`RowOrderCache` keeps the filtered and sorted row positions
  for a dataflow between window requests (#993), so a scroll through
  a sorted or searched grid filters and sorts once, not once per page.
"""
import os
import traceback
import weakref
from collections import OrderedDict
from typing import Any, Mapping, Optional
from io import BytesIO

import polars as pl

from buckaroo.dataflow.dataflow import CustomizableDataflow
from buckaroo.dataflow.styling_core import InitSD
from buckaroo.dataflow.autocleaning import PandasAutocleaning
from buckaroo.customizations.pl_autocleaning_conf import NoCleaningConfPl
from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
from buckaroo.polars_buckaroo import (
    PLSampling, local_analysis_klasses, prepare_df_for_serialization)
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


def get_metadata_polars(df: pl.DataFrame, path: str) -> dict:
    columns = [{"name": str(c), "dtype": str(d)} for c, d in zip(df.columns, df.dtypes)]
    return {"path": path, "rows": len(df), "columns": columns}


def create_polars_dataflow(df, column_config_overrides=None, extra_grid_config=None,
        init_sd: InitSD | None = None) -> PolarsServerDataflow:
    return PolarsServerDataflow(df, column_config_overrides=column_config_overrides,
        extra_grid_config=extra_grid_config, init_sd=init_sd, skip_main_serial=True)


class RowOrderCache:
    """Row positions for the infinite handler, per dataflow (#993).

    Two bounded maps, both keyed under the current ``processed_df``:

    * ``search_string`` → ``UInt32`` positions in ``processed_df`` of the
      rows matching the search (``None`` for the empty search: every row).
    * ``(search_string, sort column, descending)`` → ``arg_sort`` order
      of that column over the filtered rows, as positions within the
      filtered frame.

    A window is served by gathering ``order[start:end]`` out of
    ``processed_df`` rather than by sorting a row-indexed copy of the
    whole frame, which at 10.8M rows cost 4.5 s and a second full frame
    per page. An entry is 4 bytes per row.

    ``processed_df`` is tracked by weakref: a dataflow rerun replaces it
    and the next lookup drops every entry, without the cache keeping the
    old frame alive in the meantime.
    """
    max_entries = 4

    def __init__(self) -> None:
        self._df_ref: Optional[weakref.ref] = None
        self._filtered: "OrderedDict[str, Optional[pl.Series]]" = OrderedDict()
        self._orders: "OrderedDict[tuple[str, str, bool], pl.Series]" = OrderedDict()

    def _sync(self, processed_df: pl.DataFrame) -> None:
        if self._df_ref is None or self._df_ref() is not processed_df:
            self._filtered.clear()
            self._orders.clear()
            self._df_ref = weakref.ref(processed_df)

    @staticmethod
    def _remember(entries: OrderedDict, key, value):
        entries[key] = value
        while len(entries) > RowOrderCache.max_entries:
            entries.popitem(last=False)
        return value

    def filtered_positions(self, processed_df: pl.DataFrame, search_string: str) -> Optional[pl.Series]:
        """Positions of the rows matching ``search_string``; ``None`` when
        there is no search, so callers can slice ``processed_df`` directly."""
        self._sync(processed_df)
        if search_string in self._filtered:
            self._filtered.move_to_end(search_string)
            return self._filtered[search_string]
        if not search_string:
            positions = None
        else:
            string_cols = [c for c, dt in zip(processed_df.columns, processed_df.dtypes)
                if dt == pl.String]
            if string_cols:
                mask = pl.any_horizontal(
                    pl.col(c).str.contains(search_string, literal=True)
                    for c in string_cols)
                positions = processed_df.select(pl.arg_where(mask)).to_series()
            else:
                # No string columns to search → no matches. ``search_df_str``
                # starts from an all-False mask and only ORs over string/object
                # columns, so a non-empty search on a numeric-only frame
                # produces an empty result. Matching that here keeps the UI
                # honest: a search term should never silently appear unfiltered.
                positions = pl.Series(dtype=pl.UInt32)
        return self._remember(self._filtered, search_string, positions)

    def sort_order(self, processed_df: pl.DataFrame, search_string: str,
            sort_column: str, descending: bool) -> pl.Series:
        """``arg_sort`` of ``sort_column`` over the filtered rows: positions
        within the filtered frame, in display order."""
        positions = self.filtered_positions(processed_df, search_string)
        key = (search_string, sort_column, descending)
        if key in self._orders:
            self._orders.move_to_end(key)
            return self._orders[key]
        column = processed_df.get_column(sort_column)
        if positions is not None:
            column = column.gather(positions)
        # Same defaults as ``DataFrame.sort`` (nulls first, not stable), so
        # the order matches what sorting the frame produced.
        return self._remember(self._orders, key, column.arg_sort(descending=descending))


_row_order_caches: "weakref.WeakKeyDictionary[Any, RowOrderCache]" = weakref.WeakKeyDictionary()


def row_order_cache_for(dataflow) -> RowOrderCache:
    """The dataflow's :class:`RowOrderCache`, created on first use. Held
    weakly, so it is released with the dataflow (and its session)."""
    cache = _row_order_caches.get(dataflow)
    if cache is None:
        cache = _row_order_caches[dataflow] = RowOrderCache()
    return cache


def handle_infinite_request_buckaroo_polars(
    dataflow: PolarsServerDataflow, payload_args: dict, search_string: str = ""
) -> tuple[Mapping[str, Any], bytes]:
    """Polars analogue of :func:`handle_infinite_request_buckaroo`.

    ``search_string`` is the live-typed filter (#838) — applied as a
    literal substring match across all polars ``String`` columns.
    Literal (``literal=True``) so user typing isn't treated as regex;
    this matches the pandas server path's ``search_df_str`` semantics.

    Filtered positions and sort orders come from the dataflow's
    :class:`RowOrderCache`; only the window's rows are gathered from
    ``processed_df``. The ``index`` column is the row's position in the
    filtered frame, as ``with_row_index()`` before the sort gave it.
    """
    from buckaroo.server.window import clamp_window

    _unused, processed_df, merged_sd = dataflow.widget_args_tuple
    if processed_df is None:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0}, b"")
    try:
        cache = row_order_cache_for(dataflow)
        positions = cache.filtered_positions(processed_df, search_string)
        n_rows = len(processed_df) if positions is None else len(positions)

        start, end = clamp_window(payload_args.get("start"), payload_args.get("end"), n_rows)

        sort = payload_args.get("sort")
        if sort:
            descending = payload_args.get("sort_direction") != "asc"
            converted_sort_column = merged_sd[sort]["orig_col_name"]
            order = cache.sort_order(processed_df, search_string, converted_sort_column, descending)
            window = order[start:end]
            rows = window if positions is None else positions.gather(window)
            slice_df = processed_df.select(pl.all().gather(rows)).insert_column(0, window.alias("index"))
        elif positions is None:
            slice_df = processed_df[start:end].with_row_index(offset=start)
        else:
            slice_df = processed_df.select(pl.all().gather(positions[start:end])).with_row_index(offset=start)

        out = BytesIO()
        prepare_df_for_serialization(slice_df).write_parquet(out, compression="uncompressed")
        # Native polars parquet — strings are not JSON-wrapped.
        return make_infinite_resp(payload_args, n_rows, out.getvalue(), json_columns=[])
    except Exception:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0,
            "error_info": traceback.format_exc()}, b"")
