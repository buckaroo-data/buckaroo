"""Static embedding artifact generation for buckaroo.

Generate self-contained artifacts from DataFrames that can be rendered
in static HTML without a notebook kernel or server.

Both df_data and summary_stats_data are serialized as parquet b64
for compact transport. The JS side decodes them via resolveDFDataAsync().
"""
import base64
import json
from io import BytesIO
from pathlib import Path

import pandas as pd

from buckaroo.serialization_utils import (prepare_df_for_serialization, _json_encode_cell, _coerce_for_json)
from buckaroo.dataflow.widget_extension_utils import configure_buckaroo
from buckaroo.buckaroo_widget import BuckarooWidget


def _df_to_parquet_b64_tagged(df: pd.DataFrame) -> dict:
    """Serialize a DataFrame to a tagged parquet-b64 payload.

    Uses pyarrow for parquet serialization. Object/category columns are
    JSON-encoded per cell (same convention as sd_to_parquet_b64) so the
    JS side can decode them uniformly via parseParquetRow().

    Returns {'format': 'parquet_b64', 'data': '<base64 string>'}
    """
    df2 = prepare_df_for_serialization(df)
    if not isinstance(df.index, pd.MultiIndex):
        df2['level_0'] = df2['index']

    # Coerce types that hyparquet can't decode (Period, Interval, Timedelta, bytes)
    df2 = _coerce_for_json(df2)

    # Convert PyArrow-backed string columns to object dtype (pandas 3.0+)
    for col in df2.columns:
        if (pd.api.types.is_string_dtype(df2[col].dtype)
                and not pd.api.types.is_object_dtype(df2[col].dtype)):
            df2[col] = df2[col].astype('object')

    # JSON-encode object/category columns (except index columns which
    # the JS side keeps as-is without JSON.parse)
    obj_cols = df2.select_dtypes(['object', 'category']).columns.tolist()
    for col in obj_cols:
        if col not in ('index', 'level_0'):
            df2[col] = df2[col].apply(_json_encode_cell)

    buf = BytesIO()
    df2.to_parquet(buf, engine='pyarrow')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('ascii')
    return {'format': 'parquet_b64', 'data': b64}


def prepare_buckaroo_artifact(df, column_config_overrides=None,
                               extra_pinned_rows=None, pinned_rows=None,
                               extra_analysis_klasses=None,
                               analysis_klasses=None,
                               embed_type="DFViewer"):
    """Generate a static artifact dict from a DataFrame.

    The artifact contains all data needed to render a buckaroo table
    without a server or kernel. Both df_data and summary_stats_data
    are serialized as parquet b64 for compact transport.

    Parameters
    ----------
    df : pd.DataFrame, pl.DataFrame, str, or Path
        The data source. Strings and Paths are read as files.
    column_config_overrides : dict, optional
        Column-specific display configuration overrides.
    extra_pinned_rows, pinned_rows : list, optional
        Additional or replacement pinned summary rows.
    extra_analysis_klasses, analysis_klasses : list, optional
        Additional or replacement analysis classes.
    embed_type : str, optional
        ``"DFViewer"`` (default) for a plain table, or ``"Buckaroo"`` for the
        full buckaroo experience with the summary_stats/main display switcher.

    Returns
    -------
    dict
        Artifact dict. Always includes ``embed_type``.
        When ``embed_type="DFViewer"``: ``df_data``, ``df_viewer_config``,
        ``summary_stats_data``.
        When ``embed_type="Buckaroo"``: additionally ``df_display_args``,
        ``df_data_dict``, ``df_meta``, ``buckaroo_options``, ``buckaroo_state``.
    """
    if embed_type not in ("DFViewer", "Buckaroo"):
        raise ValueError(f"embed_type must be 'DFViewer' or 'Buckaroo', got {embed_type!r}")

    # Handle file paths
    if isinstance(df, (str, Path)):
        df = _read_file(Path(df))

    # Handle polars DataFrames
    WidgetKls = BuckarooWidget
    try:
        import polars as pl
        if isinstance(df, (pl.DataFrame, pl.LazyFrame)):
            from buckaroo.polars_buckaroo import PolarsBuckarooWidget
            WidgetKls = PolarsBuckarooWidget
            if isinstance(df, pl.LazyFrame):
                df = df.collect()
    except ImportError:
        pass

    BuckarooKls = configure_buckaroo(
        WidgetKls,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses,
        analysis_klasses=analysis_klasses)

    bw = BuckarooKls(df, column_config_overrides=column_config_overrides)

    df_viewer_config = bw.df_display_args['dfviewer_special']['df_viewer_config']
    summary_stats_data = bw.df_data_dict['all_stats']  # already parquet b64 tagged

    # Serialize the main data as parquet b64.
    # The widget stores processed data on its inner dataflow object.
    processed_df = bw.dataflow.processed_df
    from buckaroo.serialization_utils import force_to_pandas
    serializable_df = force_to_pandas(
        bw.sampling_klass.serialize_sample(processed_df))
    df_data = _df_to_parquet_b64_tagged(serializable_df)

    artifact = {
        'embed_type': embed_type,
        'df_data': df_data,
        'df_viewer_config': df_viewer_config,
        'summary_stats_data': summary_stats_data}

    if embed_type == "Buckaroo":
        # Include the full widget state for the StatusBar display switcher.
        # df_data_dict values are already parquet_b64 tagged from the widget.
        # We also add the main data under its expected key.
        df_data_dict = dict(bw.df_data_dict)
        # The widget's df_data_dict has summary stats keyed by name,
        # but the main data needs to be keyed as "main" for the switcher.
        df_data_dict['main'] = df_data

        artifact['df_display_args'] = dict(bw.df_display_args)
        artifact['df_data_dict'] = df_data_dict
        artifact['df_meta'] = dict(bw.df_meta)
        artifact['buckaroo_options'] = dict(bw.buckaroo_options)
        artifact['buckaroo_state'] = dict(bw.buckaroo_state)

    return artifact


def _read_file(path: Path):
    """Read a file into a DataFrame, trying polars first, then pandas."""
    suffix = path.suffix.lower()
    try:
        import polars as pl
        if suffix == '.parquet':
            return pl.read_parquet(path)
        elif suffix == '.csv':
            return pl.read_csv(path)
        elif suffix in ('.jsonl', '.ndjson'):
            return pl.read_ndjson(path)
        elif suffix == '.json':
            return pl.read_json(path)
        else:
            return pl.read_csv(path)
    except ImportError:
        if suffix == '.parquet':
            return pd.read_parquet(path)
        elif suffix == '.csv':
            return pd.read_csv(path)
        elif suffix in ('.json', '.jsonl', '.ndjson'):
            return pd.read_json(path, lines=(suffix in ('.jsonl', '.ndjson')))
        else:
            return pd.read_csv(path)


def artifact_to_json(artifact: dict) -> str:
    """Serialize an artifact dict to a JSON string."""
    return json.dumps(artifact, default=str)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="static-embed.css">
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; }}
  #root {{ width: 100%; height: 100vh; }}
</style>
</head>
<body>
<div id="root"></div>
<script id="buckaroo-data" type="application/json">{artifact_json}</script>
<script type="module" src="static-embed.js"></script>
</body>
</html>
"""


def to_html(df, title="Buckaroo", embed_type="DFViewer", **kwargs) -> str:
    """Generate an HTML string that renders a buckaroo table.

    The HTML references ``static-embed.js`` and ``static-embed.css``
    which must be served alongside it (produced by the JS build).

    Parameters
    ----------
    df : pd.DataFrame, pl.DataFrame, str, or Path
        The data source.
    title : str
        HTML page title.
    embed_type : str, optional
        ``"DFViewer"`` (default) for a plain table, or ``"Buckaroo"`` for
        the full experience with summary_stats/main display switcher.
    **kwargs
        Passed through to prepare_buckaroo_artifact().

    Returns
    -------
    str
        Complete HTML document string.
    """
    artifact = prepare_buckaroo_artifact(df, embed_type=embed_type, **kwargs)
    return _HTML_TEMPLATE.format(title=title, artifact_json=artifact_to_json(artifact))
