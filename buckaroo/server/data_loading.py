import os
import pandas as pd
from buckaroo.serialization_utils import to_parquet
from buckaroo.df_util import old_col_new_col


def load_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    elif ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    elif ext == ".parquet":
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
