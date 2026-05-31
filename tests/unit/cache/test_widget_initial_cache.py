"""Widget-side initial-load cache mechanism.

``BuckarooWidgetBase`` accepts an optional ``initial_cache=`` bundle. After the
widget builds its dataflow, a matching bundle (handshake passes) hydrates the
widget's display traits from the cache; a mismatch warns and keeps the
freshly-computed values. This is the *same* validate-don't-trust path the server
runs — mechanism only, no Jupyter store/driver/prewarm (per scope).

The bundle is built with the widget's own analysis klasses + sampling so the
config_id matches; we tag a sentinel onto the bundle's df_meta to prove the
replay actually ran (vs the widget's own computation, which equals the bundle's
on a match). See docs/initial-load-cache-design.md.
"""
import pandas as pd
import pytest

from buckaroo.buckaroo_widget import BuckarooInfiniteWidget, InfinitePdSampling
from buckaroo.cache.initial_cache import get_initial_cache_data


def _matching_bundle(df):
    # Same klasses + sampling as the widget ⇒ the handshake's config_id matches.
    _cid, bundle = get_initial_cache_data(
        df, analysis_klasses=BuckarooInfiniteWidget.analysis_klasses,
        sampling_klass=InfinitePdSampling)
    return bundle


def test_widget_replays_matching_bundle():
    df = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
    bundle = _matching_bundle(df)
    bundle.df_meta = {**bundle.df_meta, 'sentinel': 'from_cache'}
    w = BuckarooInfiniteWidget(df, initial_cache=bundle)
    # The sentinel only reaches the widget if apply_initial_cache ran.
    assert w.df_meta.get('sentinel') == 'from_cache'
    assert 'main' in w.df_display_args


def test_widget_warns_and_ignores_mismatch():
    df = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
    bundle = _matching_bundle(df)
    bundle.config_id = 'deadbeef0000'  # force a config_id mismatch
    bundle.df_meta = {**bundle.df_meta, 'sentinel': 'from_cache'}
    with pytest.warns(UserWarning):
        w = BuckarooInfiniteWidget(df, initial_cache=bundle)
    # Mismatch ⇒ the bundle is ignored; the widget shows its own computed meta.
    assert 'sentinel' not in w.df_meta
    assert w.df_meta['total_rows'] == 3


def test_widget_without_initial_cache_constructs_normally():
    # The new kwarg must default cleanly — no bundle, normal construction.
    df = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
    w = BuckarooInfiniteWidget(df)
    assert w.df_meta['total_rows'] == 3
    assert 'main' in w.df_display_args
