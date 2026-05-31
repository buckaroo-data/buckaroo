"""Tests for the keyed summary-stats cache.

The cache maps an op-chain hash to a parquet-b64 SD blob. Three pointer
traits — raw/clean/filt — tell the frontend which entry to read for
each scope. The invariant that matters: a state change that doesn't
move a scope's chain must not produce a new cache entry for that scope.
"""
import pandas as pd
import pytest

from buckaroo import BuckarooWidget
from buckaroo.customizations.pandas_commands import (
    DropCol, FillNA, GroupBy, NoOp, SafeInt, Search)
from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf
from buckaroo.customizations.pd_stats_v2 import PD_AUTOCLEAN_DEFAULT_V2
from buckaroo.dataflow.autocleaning import AutocleaningConfig, PandasAutocleaning
from buckaroo.dataflow.sd_cache import hash_chain, split_chain_by_scope
from buckaroo.jlisp.lisp_utils import s, sA, sQ


class _Conf(AutocleaningConfig):
    autocleaning_analysis_klasses = PD_AUTOCLEAN_DEFAULT_V2
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name = 'default'


class _CacheWidget(BuckarooWidget):
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = (_Conf, NoCleaningConf)


@pytest.fixture
def dirty_df():
    return pd.DataFrame({'a': [10, 20, 30, 40, 10, 20.3, 5, None, None, None],
        'b': ['3', '4', 'a', '5', '5', 'b', 'b', None, None, None]})


def test_chain_hash_is_deterministic():
    chain = [[sQ('search'), s('df'), 'col', 'needle']]
    assert hash_chain(chain) == hash_chain(chain)
    assert hash_chain([]) != hash_chain(chain)


def test_split_chain_separates_quick_commands_from_cleaning():
    """Quick-command ops move with the filter; cleaning ops survive a filter flip."""
    auto_op = [sA('safe_int'), s('df'), 'a']
    quick_op = [sQ('search'), s('df'), 'col', 'needle']
    chains = split_chain_by_scope([auto_op, quick_op])
    assert chains['raw'] == []
    assert chains['clean'] == [auto_op]
    assert chains['filt'] == [auto_op, quick_op]


def test_cache_populates_on_widget_init(dirty_df):
    """After construction the cache has one entry per scope, and each
    pointer trait points to a real entry."""
    bw = _CacheWidget(dirty_df, debug=False)
    df = bw.dataflow

    assert df.raw_sd_key, "raw_sd_key should be populated"
    assert df.clean_sd_key, "clean_sd_key should be populated"
    assert df.filt_sd_key, "filt_sd_key should be populated"

    cache = df.summary_stats_cache
    # raw and filt always exist; clean equals filt when no filter is
    # active (no quick-command ops applied yet), so the cache can have
    # 2 or 3 distinct entries depending on whether any quick command
    # is in operations at init.
    assert df.raw_sd_key in cache
    assert df.clean_sd_key in cache
    assert df.filt_sd_key in cache


def test_filter_flip_only_grows_filt_entry(dirty_df):
    """When ``quick_command_args`` changes, raw and clean pointers must
    not move and their cache entries must already be present (cache
    hit). Only the filt entry gets recomputed."""
    bw = _CacheWidget(dirty_df, debug=False)
    df = bw.dataflow

    # Cleaning method first, so we have a non-empty clean chain.
    bw.buckaroo_state = {'cleaning_method': 'default', 'post_processing': '', 'sampled': False, 'show_commands': 'on',
        'df_display': 'main', 'search_string': '', 'quick_command_args': {}}
    raw_before = df.raw_sd_key
    clean_before = df.clean_sd_key
    filt_before = df.filt_sd_key
    cache_size_before = len(df.summary_stats_cache)

    # Apply a filter — only the filt scope's chain should change.
    bw.buckaroo_state = {**bw.buckaroo_state, 'quick_command_args': {'search': ['needle']}}

    assert df.raw_sd_key == raw_before, "raw pointer must not move on filter flip"
    assert df.clean_sd_key == clean_before, "clean pointer must not move on filter flip"
    assert df.filt_sd_key != filt_before, "filt pointer must change on filter flip"

    # Cache grew by at most one entry (the new filt scope). Raw and
    # clean were cache hits.
    assert len(df.summary_stats_cache) == cache_size_before + 1
    assert raw_before in df.summary_stats_cache
    assert clean_before in df.summary_stats_cache
