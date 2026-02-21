import os
import traceback
from io import BytesIO
import pandas as pd
import polars as pl
from buckaroo.serialization_utils import to_parquet, pd_to_obj, check_and_fix_df
from buckaroo.df_util import old_col_new_col, to_chars

from buckaroo.dataflow.dataflow import CustomizableDataflow
from buckaroo.dataflow.dataflow_extras import Sampling
from buckaroo.dataflow.autocleaning import PandasAutocleaning
from buckaroo.dataflow.styling_core import StylingAnalysis
from buckaroo.customizations.analysis import (
    TypingStats, DefaultSummaryStats, ComputedDefaultSummaryStats)
from buckaroo.customizations.histogram import Histogram
from buckaroo.customizations.styling import DefaultSummaryStatsStyling, DefaultMainStyling
from buckaroo.customizations.pd_autoclean_conf import CleaningConf, NoCleaningConf
from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2


class ServerSampling(Sampling):
    """Sampling for headless server mode — matches InfinitePdSampling."""
    serialize_limit = -1  # infinite mode
    pre_limit = 1_000_000

    @classmethod
    def pre_stats_sample(kls, df):
        df = check_and_fix_df(df)
        if len(df.columns) > kls.max_columns:
            df = df[df.columns[:kls.max_columns]]
        if kls.pre_limit and len(df) > kls.pre_limit:
            sampled = df.sample(kls.pre_limit)
            if isinstance(sampled, pd.DataFrame):
                return sampled.sort_index()
            return sampled
        return df


class ServerDataflow(CustomizableDataflow):
    """Headless dataflow matching BuckarooInfiniteWidget's pipeline."""
    sampling_klass = ServerSampling
    autocleaning_klass = PandasAutocleaning
    DFStatsClass = DfStatsV2
    autoclean_conf = tuple([CleaningConf, NoCleaningConf])
    analysis_klasses = [
        TypingStats, DefaultSummaryStats,
        Histogram,
        ComputedDefaultSummaryStats,
        StylingAnalysis,
        DefaultSummaryStats,
        DefaultSummaryStatsStyling, DefaultMainStyling,
    ]

    def _df_to_obj(self, df):
        # No sampling — matches BuckarooInfiniteWidget._df_to_obj
        return pd_to_obj(df)


def create_dataflow(df: pd.DataFrame) -> ServerDataflow:
    """Instantiate the full Buckaroo analysis pipeline headlessly."""
    return ServerDataflow(df, skip_main_serial=True)


def get_buckaroo_display_state(dataflow: ServerDataflow) -> dict:
    """Extract all state needed by the JS BuckarooInfiniteWidget."""
    return {
        "df_data_dict": dataflow.df_data_dict,
        "df_display_args": dataflow.df_display_args,
        "df_meta": dataflow.df_meta,
        "buckaroo_options": dataflow.buckaroo_options,
        "buckaroo_state": {
            "cleaning_method": "",
            "post_processing": "",
            "sampled": False,
            "show_commands": False,
            "df_display": "main",
            "search_string": "",
            "quick_command_args": {},
        },
        "command_config": dataflow.command_config,
        "operation_results": {
            "transformed_df": {"schema": {"fields": []}, "data": []},
            "generated_py_code": "# server mode",
        },
        "operations": [],
    }


def handle_infinite_request_buckaroo(
    dataflow: ServerDataflow, payload_args: dict
) -> tuple[dict, bytes]:
    """Infinite scroll handler using the dataflow's processed_df and merged_sd."""
    start = payload_args["start"]
    end = payload_args["end"]
    _unused, processed_df, merged_sd = dataflow.widget_args_tuple
    if processed_df is None:
        return (
            {"type": "infinite_resp", "key": payload_args, "data": [], "length": 0},
            b"",
        )

    try:
        sort = payload_args.get("sort")
        if sort:
            ascending = payload_args.get("sort_direction") == "asc"
            # merged_sd maps renamed col -> stats dict with 'orig_col_name'
            converted_sort_column = merged_sd[sort]["orig_col_name"]
            sorted_df = processed_df.sort_values(
                by=[converted_sort_column], ascending=ascending
            )
            slice_df = sorted_df[start:end]
        else:
            slice_df = processed_df[start:end]

        parquet_bytes = to_parquet(slice_df)
        msg = {
            "type": "infinite_resp",
            "key": payload_args,
            "data": [],
            "length": len(processed_df),
        }
        return msg, parquet_bytes
    except Exception:
        return (
            {
                "type": "infinite_resp",
                "key": payload_args,
                "data": [],
                "length": 0,
                "error_info": traceback.format_exc(),
            },
            b"",
        )


def load_file_lazy(path: str) -> pl.LazyFrame:
    """Open a file as a Polars LazyFrame — no data read until sliced."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".parquet", ".parq"):
        return pl.scan_parquet(path)
    elif ext == ".csv":
        return pl.scan_csv(path)
    elif ext == ".tsv":
        return pl.scan_csv(path, separator="\t")
    elif ext == ".json":
        return pl.scan_ndjson(path)
    else:
        raise ValueError(f"Unsupported file format for lazy loading: {ext}")


def get_metadata_lazy(ldf: pl.LazyFrame, path: str) -> dict:
    schema = ldf.collect_schema()
    col_names = schema.names()
    col_dtypes = schema.dtypes()
    total_rows = int(ldf.select(pl.len()).collect().item())
    columns = [{"name": n, "dtype": str(d)} for n, d in zip(col_names, col_dtypes)]
    return {"path": path, "rows": total_rows, "columns": columns}


def get_display_state_lazy(ldf: pl.LazyFrame) -> tuple[dict, dict, dict]:
    """Return (display_state, orig_to_rw, rw_to_orig) for a lazy frame."""
    schema = ldf.collect_schema()
    col_names = schema.names()
    orig_to_rw = {name: to_chars(i) for i, name in enumerate(col_names)}
    rw_to_orig = {v: k for k, v in orig_to_rw.items()}

    column_config = [
        {"col_name": rw, "header_name": orig, "displayer_args": {"displayer": "obj"}}
        for orig, rw in orig_to_rw.items()
    ]
    df_viewer_config = {
        "pinned_rows": [],
        "column_config": column_config,
        "left_col_configs": [{"col_name": "index", "header_name": "", "displayer_args": {"displayer": "obj"}}],
    }
    display_state = {
        "df_meta": {"total_rows": 0},  # filled in after row count
        "df_data_dict": {"main": [], "all_stats": [], "empty": []},
        "df_display_args": {
            "main": {
                "data_key": "main",
                "df_viewer_config": df_viewer_config,
                "summary_stats_key": "all_stats",
            }
        },
    }
    return display_state, orig_to_rw, rw_to_orig


def handle_infinite_request_lazy(
    ldf: pl.LazyFrame,
    orig_to_rw: dict,
    rw_to_orig: dict,
    total_rows: int,
    payload_args: dict,
) -> tuple[dict, bytes]:
    """Serve an infinite-scroll slice from a Polars LazyFrame."""
    start = int(payload_args.get("start", 0))
    end = int(payload_args.get("end", 0))

    base = ldf.select(pl.all())
    sort_col = payload_args.get("sort")
    if sort_col:
        orig_sort = rw_to_orig.get(sort_col, sort_col)
        ascending = payload_args.get("sort_direction") == "asc"
        base = base.sort(orig_sort, descending=not ascending)

    slice_len = max(end - start, 0)
    slice_df = (
        base.slice(start, slice_len)
        .with_row_index(name="index", offset=start)
        .collect()
    )

    # Rename data columns to rewritten names (matching widget behaviour)
    select_exprs = [pl.col("index")]
    for orig, rw in orig_to_rw.items():
        if orig in slice_df.columns:
            select_exprs.append(pl.col(orig).alias(rw))
    slice_df = slice_df.select(select_exprs)

    out = BytesIO()
    slice_df.write_parquet(out, compression="uncompressed")
    parquet_bytes = out.getvalue()

    msg = {"type": "infinite_resp", "key": payload_args, "data": [], "length": total_rows}
    return msg, parquet_bytes


def load_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    elif ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    elif ext in (".parquet", ".parq"):
        return pd.read_parquet(path)
    elif ext == ".json":
        return pd.read_json(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def _dtype_to_displayer(dtype) -> dict:
    """Map a pandas dtype to a Buckaroo displayer_args dict."""
    if pd.api.types.is_bool_dtype(dtype):
        return {"displayer": "boolean"}
    if pd.api.types.is_integer_dtype(dtype):
        return {"displayer": "integer", "min_digits": 1, "max_digits": 12}
    if pd.api.types.is_float_dtype(dtype):
        return {"displayer": "float", "min_fraction_digits": 1, "max_fraction_digits": 6}
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return {"displayer": "datetimeDefault"}
    return {"displayer": "obj", "max_length": 200}


def get_df_viewer_config(df: pd.DataFrame) -> dict:
    """Generate a minimal DFViewerConfig from a DataFrame's schema.

    Column configs use the renamed column names (a, b, c, ...) that
    to_parquet/prepare_df_for_serialization produces, with the original
    column name as the header_name for display.
    """
    col_rename_map = old_col_new_col(df)  # [(orig_name, "a"), (orig_name, "b"), ...]
    column_config = []
    for orig_name, renamed in col_rename_map:
        column_config.append({
            "col_name": renamed,
            "header_name": str(orig_name),
            "displayer_args": _dtype_to_displayer(df[orig_name].dtype),
        })

    # Index column shown on the left
    left_col_configs = [{
        "col_name": "index",
        "header_name": "",
        "displayer_args": {"displayer": "integer", "min_digits": 1, "max_digits": 12},
    }]

    return {
        "pinned_rows": [],
        "column_config": column_config,
        "left_col_configs": left_col_configs,
    }


def get_display_state(df: pd.DataFrame, path: str) -> dict:
    """Generate the initial state the JS client needs to render."""
    df_viewer_config = get_df_viewer_config(df)
    return {
        "df_meta": {"total_rows": len(df)},
        "df_data_dict": {"main": [], "all_stats": [], "empty": []},
        "df_display_args": {
            "main": {
                "data_key": "main",
                "df_viewer_config": df_viewer_config,
                "summary_stats_key": "all_stats",
            }
        },
    }


def get_metadata(df: pd.DataFrame, path: str) -> dict:
    columns = []
    for col in df.columns:
        columns.append({
            "name": str(col),
            "dtype": str(df[col].dtype),
        })
    return {
        "path": path,
        "rows": len(df),
        "columns": columns,
    }


def handle_infinite_request(df: pd.DataFrame, payload_args: dict) -> tuple[dict, bytes]:
    """Extract of BuckarooInfiniteWidget._handle_payload_args — transport-agnostic.

    The sort column name from the JS client uses renamed column names
    (a, b, c, ...) since that's what the Parquet data uses. We need to
    map it back to the original column name for sorting.
    """
    start = payload_args["start"]
    end = payload_args["end"]

    sort = payload_args.get("sort")
    if sort:
        # Map renamed column back to original name
        rename_map = {renamed: orig for orig, renamed in old_col_new_col(df)}
        orig_sort_col = rename_map.get(sort, sort)
        ascending = payload_args.get("sort_direction") == "asc"
        sorted_df = df.sort_values(by=[orig_sort_col], ascending=ascending)
        slice_df = sorted_df[start:end]
    else:
        slice_df = df[start:end]

    parquet_bytes = to_parquet(slice_df)
    msg = {
        "type": "infinite_resp",
        "key": payload_args,
        "data": [],
        "length": len(df),
    }
    return msg, parquet_bytes
