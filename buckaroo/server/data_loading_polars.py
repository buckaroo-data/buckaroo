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
"""
import os
import traceback
from io import BytesIO

import polars as pl

from buckaroo.dataflow.dataflow import CustomizableDataflow
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


class PolarsServerDataflow(CustomizableDataflow):
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


def create_polars_dataflow(df, column_config_overrides=None, extra_grid_config=None, init_sd=None) -> PolarsServerDataflow:
    return PolarsServerDataflow(df, column_config_overrides=column_config_overrides,
        extra_grid_config=extra_grid_config, init_sd=init_sd, skip_main_serial=True)


def handle_infinite_request_buckaroo_polars(
    dataflow: PolarsServerDataflow, payload_args: dict, search_string: str = ""
) -> tuple[dict, bytes]:
    """Polars analogue of :func:`handle_infinite_request_buckaroo`.

    ``search_string`` is the live-typed filter (#838) — applied as a
    literal substring match across all polars ``String`` columns.
    Literal (``literal=True``) so user typing isn't treated as regex;
    this matches the pandas server path's ``search_df_str`` semantics.
    """
    from buckaroo.server.window import clamp_window

    _unused, processed_df, merged_sd = dataflow.widget_args_tuple
    if processed_df is None:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0}, b"")
    try:
        if search_string:
            string_cols = [c for c, dt in zip(processed_df.columns, processed_df.dtypes)
                if dt == pl.String]
            if string_cols:
                mask = pl.any_horizontal(
                    pl.col(c).str.contains(search_string, literal=True)
                    for c in string_cols)
                filtered_df = processed_df.filter(mask)
            else:
                # No string columns to search → no matches. ``search_df_str``
                # starts from an all-False mask and only ORs over string/object
                # columns, so a non-empty search on a numeric-only frame
                # produces an empty result. Matching that here keeps the UI
                # honest: a search term should never silently appear unfiltered.
                filtered_df = processed_df.clear()
        else:
            filtered_df = processed_df

        start, end = clamp_window(
            payload_args.get("start"), payload_args.get("end"), len(filtered_df))

        sort = payload_args.get("sort")
        if sort:
            ascending = payload_args.get("sort_direction") == "asc"
            converted_sort_column = merged_sd[sort]["orig_col_name"]
            sorted_df = filtered_df.with_row_index().sort(
                converted_sort_column, descending=not ascending)
            slice_df = sorted_df[start:end]
        else:
            slice_df = filtered_df.with_row_index()[start:end]

        out = BytesIO()
        prepare_df_for_serialization(slice_df).write_parquet(out, compression="uncompressed")
        return make_infinite_resp(payload_args, len(filtered_df), out.getvalue())
    except Exception:
        return ({"type": "infinite_resp", "key": payload_args, "length": 0,
            "error_info": traceback.format_exc()}, b"")
