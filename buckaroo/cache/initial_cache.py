"""Initial-load cache: producer, handshake, and consumer.

Three entry points realise the design's "serve the first render without
touching the data":

* ``get_initial_cache_data(df_or_expr, ...)`` / ``build_bundle_from_dataflow`` —
  the **producer**. Runs the analysis pipeline once and snapshots everything the
  frontend needs for the first paint into an ``InitialCacheData`` bundle: the
  prerendered ``df_display_args``, ``df_meta``, the type-tagged ``merged_sd``
  parquet (``sd_codec``), the first row window as parquet, and the
  ``config_id`` / ``column_schema`` the handshake validates against.
* ``cache_mismatch_reason(bundle, ...)`` — the **handshake**. Returns ``None``
  when the bundle provably matches the live configuration (version + config_id +
  schema), or a human-readable reason otherwise. The widget/server compute their
  *own* config_id and compare — a bundle's claim is never blindly trusted.
* ``apply_initial_cache(target, bundle, ...)`` — the **consumer**. Hydrates a
  target (widget / dataflow / server session) from the bundle alone — no
  DataFrame, no expression execution. With replay-time display overrides it
  regenerates ``df_display_args`` from a zero-row frame (styling reads only the
  summary dict + column/index structure, never row values).

Backend dispatch for ``get_initial_cache_data`` currently covers pandas; the
polars/xorq builders land with the server integration. ``build_bundle_from_dataflow``
is backend-agnostic — it reads an already-constructed dataflow, which is how the
server (holding a built ``ServerDataflow`` / ``XorqServerDataflow``) uses it. See
docs/initial-load-cache-design.md.
"""
import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from buckaroo.cache.fingerprint import config_fingerprint
from buckaroo.cache.sd_codec import deserialize_sd, serialize_sd
from buckaroo.dataflow.styling_core import build_df_display_args
from buckaroo.serialization_utils import sd_to_parquet_b64, to_parquet

# Bump when the bundle shape or replay logic changes incompatibly, so old
# bundles fail the handshake (warn + recompute) rather than mis-render.
CACHE_FORMAT_VERSION = 1

# Default first-window size — matches the design's 1000-row cached window.
DEFAULT_WINDOW = 1000


@dataclass
class InitialCacheData:
    """In-memory first-render snapshot for one (config, data) pair.

    ``sd_parquet`` and ``first_window_parquet`` hold raw parquet bytes (no b64,
    no pickle); persistence to a manifest + parquet files is the store's job.
    """
    config_id: str
    data_id: Optional[str]
    df_meta: Dict[str, Any]
    column_schema: Dict[str, Any]
    sd_parquet: bytes
    first_window_parquet: bytes
    first_window: Dict[str, int]
    df_display_args: Dict[str, Any]
    buckaroo_options: Dict[str, Any]
    command_config: Dict[str, Any]
    styling_klasses: List[str] = field(default_factory=list)
    cache_format_version: int = CACHE_FORMAT_VERSION


def extract_column_schema(df: pd.DataFrame) -> Dict[str, Any]:
    """Capture the column + index *structure* needed to (a) rebuild a zero-row
    frame for styling regeneration and (b) detect a schema drift in the handshake.

    MultiIndex columns are stored as lists-of-lists with their level names so the
    rebuilt frame reproduces the exact ``old_col_new_col`` mapping the styler keys
    off. Row values are never captured.
    """
    cols_multi = isinstance(df.columns, pd.MultiIndex)
    columns = [list(c) if isinstance(c, tuple) else c for c in df.columns]
    return {
        'columns': columns,
        'columns_multiindex': cols_multi,
        'columns_names': list(df.columns.names) if cols_multi else None,
        'dtypes': [str(dt) for dt in df.dtypes],
        'index_multiindex': isinstance(df.index, pd.MultiIndex),
        'index_names': [None if n is None else str(n) for n in df.index.names],
        'index_nlevels': df.index.nlevels}


def _zero_row_df(schema: Dict[str, Any]) -> pd.DataFrame:
    """Rebuild a 0-row DataFrame with the schema's columns + index structure.

    Styling reads only column names/order (via ``old_col_new_col``) and index
    structure (via ``get_left_col_configs``), so this regenerates identical
    ``df_display_args`` without the real frame.
    """
    cols = schema['columns']
    if schema.get('columns_multiindex'):
        columns: Any = pd.MultiIndex.from_tuples(
            [tuple(c) for c in cols], names=schema.get('columns_names'))
    else:
        columns = cols
    if schema.get('index_multiindex'):
        index: Any = pd.MultiIndex.from_arrays(
            [[] for _ in range(schema['index_nlevels'])], names=schema['index_names'])
    else:
        names = schema.get('index_names') or []
        index = pd.Index([], name=names[0] if names else None)
    return pd.DataFrame(index=index, columns=columns)


def build_bundle_from_dataflow(dataflow: Any, *, data_id: Optional[str] = None,
        window: int = DEFAULT_WINDOW, cache_version: Optional[str] = None) -> InitialCacheData:
    """Snapshot a *built* dataflow's first render into a bundle.

    Backend-agnostic: reads only the public traits a finished dataflow exposes
    (``widget_args_tuple``, ``df_display_args``, ``df_meta``, ...). This is what
    the server calls — it already holds a built ``ServerDataflow`` /
    ``XorqServerDataflow``.
    """
    _id, processed_df, merged_sd = dataflow.widget_args_tuple
    config_id = config_fingerprint(
        analysis_klasses=dataflow.analysis_klasses,
        sampling_klass=getattr(dataflow, 'sampling_klass', None),
        init_sd=getattr(dataflow, 'init_sd', None) or None,
        skip_stat_columns=getattr(dataflow, 'skip_stat_columns', None),
        cache_version=cache_version)
    total = len(processed_df)
    styling_klasses = [
        "%s.%s" % (k.__module__, getattr(k, '__qualname__', k.__name__))
        for k in dataflow.df_display_klasses.values()]
    return InitialCacheData(
        config_id=config_id, data_id=data_id,
        df_meta=dict(dataflow.df_meta),
        column_schema=extract_column_schema(processed_df),
        sd_parquet=serialize_sd(merged_sd),
        first_window_parquet=to_parquet(processed_df[0:window]),
        first_window={'start': 0, 'end': min(window, total), 'total_rows': total},
        df_display_args=copy.deepcopy(dataflow.df_display_args),
        buckaroo_options=dict(dataflow.buckaroo_options),
        command_config=dict(dataflow.command_config),
        styling_klasses=styling_klasses)


def _build_pandas_dataflow(df: pd.DataFrame, *, analysis_klasses: Any, sampling_klass: Any,
        init_sd: Any, skip_stat_columns: Any, column_config_overrides: Any, component_config: Any,
        extra_grid_config: Any, pinned_rows: Any) -> Any:
    # ServerDataflow is the headless pandas pipeline the server + widget share,
    # so a bundle built here matches what the live path produces. analysis_klasses
    # / sampling_klass are class attributes, so a custom set needs a fresh subclass
    # (the widget does the same with its InnerDataFlow).
    from buckaroo.server.data_loading import ServerDataflow
    cls = ServerDataflow
    if analysis_klasses is not None or sampling_klass is not None:
        class _CacheProducerDataflow(ServerDataflow):
            pass
        if analysis_klasses is not None:
            _CacheProducerDataflow.analysis_klasses = analysis_klasses
        if sampling_klass is not None:
            _CacheProducerDataflow.sampling_klass = sampling_klass
        cls = _CacheProducerDataflow
    return cls(df, column_config_overrides=column_config_overrides, pinned_rows=pinned_rows,
        extra_grid_config=extra_grid_config, component_config=component_config, init_sd=init_sd,
        skip_stat_columns=skip_stat_columns, skip_main_serial=True)


def get_initial_cache_data(df_or_expr: Any, *, analysis_klasses: Any = None, sampling_klass: Any = None,
        init_sd: Any = None, skip_stat_columns: Any = None, window: int = DEFAULT_WINDOW,
        data_id: Optional[str] = None, cache_version: Optional[str] = None,
        column_config_overrides: Any = None, component_config: Any = None, extra_grid_config: Any = None,
        pinned_rows: Any = None) -> Tuple[str, InitialCacheData]:
    """Producer: build the pipeline once and return ``(config_id, bundle)``.

    Display overrides passed here are baked into the bundle's baseline
    ``df_display_args``; the config_id excludes them, so re-theming at replay
    never invalidates the cache.
    """
    if not isinstance(df_or_expr, pd.DataFrame):
        raise NotImplementedError(
            "get_initial_cache_data currently builds the pipeline for pandas "
            "DataFrames; polars/xorq dispatch lands with the server integration.")
    dataflow = _build_pandas_dataflow(
        df_or_expr, analysis_klasses=analysis_klasses, sampling_klass=sampling_klass,
        init_sd=init_sd, skip_stat_columns=skip_stat_columns,
        column_config_overrides=column_config_overrides, component_config=component_config,
        extra_grid_config=extra_grid_config, pinned_rows=pinned_rows)
    bundle = build_bundle_from_dataflow(
        dataflow, data_id=data_id, window=window, cache_version=cache_version)
    return bundle.config_id, bundle


def _schema_compatible(cached: Dict[str, Any], live: Dict[str, Any]) -> bool:
    return (cached.get('columns') == live.get('columns')
        and cached.get('dtypes') == live.get('dtypes'))


def cache_mismatch_reason(bundle: InitialCacheData, *, analysis_klasses: Any,
        sampling_klass: Any = None, init_sd: Any = None, skip_stat_columns: Any = None,
        schema: Optional[Dict[str, Any]] = None, cache_version: Optional[str] = None) -> Optional[str]:
    """Return ``None`` when the bundle is safe to replay, else why it isn't.

    Validates, in order: bundle format version, the data-touching ``config_id``
    (recomputed from the *live* config — never read from the bundle), and, when a
    live ``schema`` is supplied, that its columns/dtypes match the cached ones.
    """
    if bundle.cache_format_version != CACHE_FORMAT_VERSION:
        return ("cache_format_version mismatch: bundle %r != runtime %r"
            % (bundle.cache_format_version, CACHE_FORMAT_VERSION))
    live_config_id = config_fingerprint(
        analysis_klasses=analysis_klasses, sampling_klass=sampling_klass,
        init_sd=init_sd, skip_stat_columns=skip_stat_columns, cache_version=cache_version)
    if live_config_id != bundle.config_id:
        return ("config_id mismatch: live analysis klasses / sampling / init_sd / "
            "version differ from the cached bundle")
    if schema is not None and not _schema_compatible(bundle.column_schema, schema):
        return "schema mismatch: live columns/dtypes differ from the cached bundle"
    return None


def serve_window_request(payload_args: Dict[str, Any], window: int = DEFAULT_WINDOW,
        search_string: str = "") -> bool:
    """True iff an infinite_request can be answered from the cached first window.

    The bundle caches only the head slice ``[0:window]``, unsorted and unfiltered.
    A sort, a live per-client search, a non-zero start, or an end past the cached
    window must fall through to the live source (the scroll path that warms the
    expr). ``end`` may exceed the actual row count — the cached parquet simply has
    fewer rows — so the bound is the configured ``window``, not the row total.
    """
    if search_string:
        return False
    if payload_args.get('sort'):
        return False
    start = payload_args.get('start', 0) or 0
    end = payload_args.get('end', 0) or 0
    return start == 0 and 0 <= end <= window


def apply_initial_cache(target: Any, bundle: InitialCacheData, *, df_display_klasses: Any = None,
        column_config_overrides: Any = None, component_config: Any = None, extra_grid_config: Any = None,
        pinned_rows: Any = None, sd_to_jsondf: Any = None) -> None:
    """Hydrate ``target`` from the bundle alone — no DataFrame, no execution.

    Sets ``df_data_dict`` / ``df_display_args`` / ``df_meta`` / ``buckaroo_options``
    / ``command_config``. ``df_data_dict['main']`` stays empty (rows arrive via the
    window channel); ``all_stats`` is re-derived from the cached ``merged_sd`` via
    ``sd_to_jsondf`` (default: the pandas parquet-b64 encoder; polars overrides it).

    When replay-time display overrides are supplied *and* ``df_display_klasses`` is
    given, ``df_display_args`` is regenerated from a zero-row frame so the
    overrides take effect without rebuilding the source frame. Otherwise the
    bundle's prerendered (baseline) ``df_display_args`` is used directly.
    """
    if sd_to_jsondf is None:
        sd_to_jsondf = sd_to_parquet_b64
    merged_sd = deserialize_sd(bundle.sd_parquet)
    target.df_data_dict = {'main': [], 'all_stats': sd_to_jsondf(merged_sd), 'empty': []}

    has_overrides = bool(column_config_overrides or component_config or extra_grid_config or pinned_rows)
    if has_overrides and df_display_klasses is not None:
        zdf = _zero_row_df(bundle.column_schema)
        target.df_display_args = build_df_display_args(
            df_display_klasses, merged_sd, zdf, column_config_overrides or {},
            pinned_rows=pinned_rows, extra_grid_config=extra_grid_config, component_config=component_config)
    else:
        target.df_display_args = copy.deepcopy(bundle.df_display_args)
    target.df_meta = dict(bundle.df_meta)
    target.buckaroo_options = dict(bundle.buckaroo_options)
    target.command_config = dict(bundle.command_config)
