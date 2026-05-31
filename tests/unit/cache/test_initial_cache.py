"""Tests for the initial-load cache producer / handshake / consumer.

These exercise the *backend-agnostic core* (pandas only — no xorq / polars /
server needed):

* ``get_initial_cache_data`` / ``build_bundle_from_dataflow`` — the producer
  runs the pipeline once and snapshots a bundle equal to a live dataflow's
  first render.
* ``cache_mismatch_reason`` — the handshake: matching config ⇒ ``None``;
  wrong analysis klasses / schema / version ⇒ a reason string.
* ``apply_initial_cache`` — the consumer hydrates a target from the bundle
  alone (no DataFrame), and regenerates ``df_display_args`` from a zero-row
  frame when replay-time display overrides are supplied (styling is data-free).

The xorq "expr raises on execution" hit-path proof and the server default-on
wiring land with the server integration. See docs/initial-load-cache-design.md.
"""
import types
from io import BytesIO

import pandas as pd

from buckaroo.cache.fingerprint import config_fingerprint
from buckaroo.cache.sd_codec import deserialize_sd
from buckaroo.cache.initial_cache import (
    CACHE_FORMAT_VERSION, InitialCacheData, get_initial_cache_data,
    build_bundle_from_dataflow, cache_mismatch_reason, apply_initial_cache,
    extract_column_schema)
from buckaroo.pluggable_analysis_framework.utils import filter_analysis
from buckaroo.server.data_loading import ServerDataflow, ServerSampling, create_dataflow


def _df():
    return pd.DataFrame({
        'ints': [1, 2, 3, 4, 5],
        'floats': [1.5, 2.5, 3.5, 4.5, 5.5],
        'strs': ['a', 'b', 'c', 'd', 'e'],
        'dates': pd.to_datetime(['2020-01-01', '2020-06-01', '2021-01-01', '2021-06-01', '2022-01-01'])})


def test_producer_matches_live_dataflow():
    df = _df()
    live = create_dataflow(df)
    config_id, bundle = get_initial_cache_data(df)

    assert isinstance(bundle, InitialCacheData)
    assert bundle.config_id == config_id
    assert bundle.cache_format_version == CACHE_FORMAT_VERSION
    # config_id is the fingerprint of the data-touching config — independent
    # of id(); reproducible from the klass list alone.
    assert config_id == config_fingerprint(
        analysis_klasses=ServerDataflow.analysis_klasses, sampling_klass=ServerSampling)
    # The prerendered display args + meta equal a live dataflow's, byte-for-byte.
    assert bundle.df_display_args == live.df_display_args
    assert bundle.df_meta == live.df_meta
    # merged_sd round-trips (minus value_counts) and keeps the same columns.
    live_sd = live.widget_args_tuple[2]
    assert set(deserialize_sd(bundle.sd_parquet).keys()) == set(live_sd.keys())


def test_build_bundle_from_dataflow_directly():
    # The API the server uses in increment 4: it already has a built dataflow.
    df = _df()
    dataflow = create_dataflow(df)
    bundle = build_bundle_from_dataflow(dataflow, data_id="abc123")
    assert bundle.data_id == "abc123"
    assert bundle.df_display_args == dataflow.df_display_args
    assert bundle.first_window['total_rows'] == len(df)


def test_first_window_parquet_roundtrips():
    df = _df()
    _cid, bundle = get_initial_cache_data(df, window=3)
    assert bundle.first_window == {'start': 0, 'end': 3, 'total_rows': 5}
    back = pd.read_parquet(BytesIO(bundle.first_window_parquet))
    # window cached the first 3 rows (renamed-col scheme has an 'index' col).
    assert len(back) == 3
    assert 'index' in back.columns


def test_apply_reproduces_display_without_a_dataframe():
    df = _df()
    live = create_dataflow(df)
    _cid, bundle = get_initial_cache_data(df)

    # A bare target — no DataFrame, no pipeline. Hydration is bundle-only.
    target = types.SimpleNamespace()
    apply_initial_cache(target, bundle)

    assert target.df_display_args == live.df_display_args
    assert target.df_meta == bundle.df_meta
    assert target.df_data_dict['main'] == []
    assert target.df_data_dict['empty'] == []
    # all_stats is the wire payload derived from the cached merged_sd.
    all_stats = target.df_data_dict['all_stats']
    assert isinstance(all_stats, dict) and all_stats.get('format') == 'parquet_b64'


def test_handshake_matches():
    df = _df()
    _cid, bundle = get_initial_cache_data(df)
    reason = cache_mismatch_reason(
        bundle, analysis_klasses=ServerDataflow.analysis_klasses,
        sampling_klass=ServerSampling, schema=extract_column_schema(df))
    assert reason is None


def test_handshake_wrong_analysis_klasses():
    df = _df()
    _cid, bundle = get_initial_cache_data(df)
    # Drop the last klass — a different data-touching config ⇒ config_id differs.
    fewer = ServerDataflow.analysis_klasses[:-1]
    reason = cache_mismatch_reason(
        bundle, analysis_klasses=fewer, sampling_klass=ServerSampling,
        schema=extract_column_schema(df))
    assert reason is not None
    assert 'config' in reason.lower()


def test_handshake_wrong_schema():
    df = _df()
    _cid, bundle = get_initial_cache_data(df)
    other = df.rename(columns={'ints': 'renamed'})
    reason = cache_mismatch_reason(
        bundle, analysis_klasses=ServerDataflow.analysis_klasses,
        sampling_klass=ServerSampling, schema=extract_column_schema(other))
    assert reason is not None
    assert 'schema' in reason.lower()


def test_handshake_version_mismatch():
    df = _df()
    _cid, bundle = get_initial_cache_data(df)
    bundle.cache_format_version = CACHE_FORMAT_VERSION + 1
    reason = cache_mismatch_reason(
        bundle, analysis_klasses=ServerDataflow.analysis_klasses,
        sampling_klass=ServerSampling)
    assert reason is not None
    assert 'version' in reason.lower()


def test_replay_override_parity():
    # Capture with no overrides; replay with non-trivial display knobs.
    # The replayed df_display_args must equal a live dataflow built with the
    # same knobs — proving styling regenerates from a zero-row frame.
    df = _df()
    overrides = {'ints': {'color_map_config': {
        'color_rule': 'color_categorical', 'val_column': 'ints'}}}
    component_config = {'height_fraction': 2}

    live = create_dataflow(df)
    live_with_knobs = ServerDataflow(
        df, column_config_overrides=overrides, component_config=component_config,
        skip_main_serial=True)

    _cid, bundle = get_initial_cache_data(df)
    # Sanity: the baseline bundle differs from the knob'd render.
    assert bundle.df_display_args == live.df_display_args

    df_display_klasses = filter_analysis(ServerDataflow.analysis_klasses, "df_display_name")
    target = types.SimpleNamespace()
    apply_initial_cache(
        target, bundle, df_display_klasses=df_display_klasses,
        column_config_overrides=overrides, component_config=component_config)
    assert target.df_display_args == live_with_knobs.df_display_args


def test_zero_row_df_reproduces_multiindex_col_mapping():
    # The MultiIndex risk: a zero-row frame rebuilt from the schema must
    # reproduce the exact old_col_new_col mapping the styler keys off.
    from buckaroo.cache.initial_cache import _zero_row_df
    from buckaroo.df_util import old_col_new_col

    cols = pd.MultiIndex.from_tuples(
        [('a', 'x'), ('a', 'y'), ('b', 'z')], names=['lvl1', 'lvl2'])
    df = pd.DataFrame([[1, 2, 3], [4, 5, 6]], columns=cols)
    zdf = _zero_row_df(extract_column_schema(df))
    assert len(zdf) == 0
    assert old_col_new_col(zdf) == old_col_new_col(df)
