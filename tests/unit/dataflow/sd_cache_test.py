"""Tests for the keyed summary-stats cache.

The cache maps an op-chain hash to a parquet-b64 SD blob. Three pointer
traits — raw/clean/filt — tell the frontend which entry to read for
each scope. The invariant that matters: a state change that doesn't
move a scope's chain must not produce a new cache entry for that scope.
"""
import pandas as pd
import pytest

from buckaroo import BuckarooWidget
from buckaroo.customizations.analysis import DefaultSummaryStats, PdCleaningStats
from buckaroo.customizations.pandas_commands import (
    DropCol, FillNA, GroupBy, NoOp, SafeInt, Search)
from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf
from buckaroo.dataflow.autocleaning import AutocleaningConfig, PandasAutocleaning
from buckaroo.dataflow.dataflow import CustomizableDataflow, StylingAnalysis
from buckaroo.dataflow.sd_cache import hash_chain, split_chain_by_scope
from buckaroo.jlisp.lisp_utils import s, sA, sQ
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis


class CleaningGenOps(ColAnalysis):
    requires_summary = ['int_parse_fail', 'int_parse']
    provides_defaults = {'cleaning_ops': []}

    @classmethod
    def computed_summary(kls, column_metadata):
        if column_metadata['int_parse'] > 0.3:
            return {
                'cleaning_ops': [
                    {'symbol': 'safe_int', 'meta': {'auto_clean': True}},
                    {'symbol': 'df'},
                ],
                'add_orig': True,
            }
        return {'cleaning_ops': []}


class _Conf(AutocleaningConfig):
    autocleaning_analysis_klasses = [DefaultSummaryStats, CleaningGenOps, PdCleaningStats]
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


class _CountingDataflow(CustomizableDataflow):
    """CustomizableDataflow subclass that records every ``_get_summary_sd``
    call by the row-count of the df it was passed.

    Use this to assert that ``_summary_sd`` (which calls
    ``_get_summary_sd`` on ``processed_df``) hits the cache on a
    warm-cache state_change instead of recomputing. The raw/clean
    scopes are populated through a separate call path inside
    ``_populate_sd_cache`` — those calls also land here but are easy
    to distinguish by their row-count (raw/clean run on the full
    ``sampled_df``, the filt scope runs on the filtered
    ``processed_df``).
    """
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = tuple([_Conf, NoCleaningConf])
    analysis_klasses = [StylingAnalysis, DefaultSummaryStats]

    def __init__(self, *args, **kwargs):
        self.summary_sd_calls = []
        super().__init__(*args, **kwargs)

    def _get_summary_sd(self, df):
        try:
            self.summary_sd_calls.append(len(df))
        except Exception:
            self.summary_sd_calls.append(-1)
        return super()._get_summary_sd(df)


def test_warm_filt_cache_skips_get_summary_sd_on_state_change(dirty_df):
    """Issue #814 regression.

    A state_change that re-applies a previously-computed filter must
    NOT call ``_get_summary_sd`` through ``_summary_sd`` again — the
    filt scope's cached entry from the first application must be
    reused.

    Cycle: filter=abc → clear → filter=abc. The third state-change
    must not run ``_get_summary_sd`` on any df with the filt scope's
    row count (the only "new compute" the cache is supposed to skip).

    Currently fails because ``_summary_sd`` reads ``self.operations``
    for its cache key, but ``self.operations`` is the PRIOR state's
    chain at the moment ``_summary_sd`` fires (during
    ``self.cleaned = result`` — before
    ``self.operations = result[3]``). So the cache lookup never sees
    the new chain's entry — actually, today there is no cache lookup
    at all, so the call always happens. The fix re-introduces the
    lookup but keys it off ``self.merged_operations`` (== the freshly
    set ``self.cleaned[3]``) so the right entry is found.
    """
    dfc = _CountingDataflow(dirty_df, debug=False)

    # Apply filter the first time — populates filt_key_abc.
    dfc.quick_command_args = {'search': ['10']}
    filt_rows_first_apply = len(dfc.processed_df)
    raw_rows = len(dfc.sampled_df)
    assert filt_rows_first_apply < raw_rows, (
        "precondition: search should have reduced rows"
    )

    # Clear filter — back to empty-filter chain (cache hit from init).
    dfc.quick_command_args = {}

    calls_before_replay = list(dfc.summary_sd_calls)

    # Replay the same filter. This MUST be a cache hit in _summary_sd —
    # no _get_summary_sd call on the filtered (smaller-row) df.
    dfc.quick_command_args = {'search': ['10']}

    new_calls = dfc.summary_sd_calls[len(calls_before_replay):]
    filt_scope_calls = [n for n in new_calls if n == filt_rows_first_apply]
    assert filt_scope_calls == [], (
        f"warm-cache filter replay must skip _get_summary_sd for the "
        f"filt scope (row-count={filt_rows_first_apply}). Saw "
        f"{len(filt_scope_calls)} call(s) — _summary_sd missed the "
        f"cache and recomputed. New calls in this state_change: "
        f"{new_calls}."
    )


def test_summary_sd_uses_new_state_chain_not_prior():
    """Regression for the cascade-ordering bug that motivated the
    original removal of the ``_summary_sd`` cache lookup
    (commit 5bc7bbfb).

    If ``_summary_sd`` keys off ``self.operations`` instead of the
    fresh chain in ``self.cleaned[3]``, then on a state_change the
    cached entry it returns corresponds to the PRIOR state's chain —
    so ``summary_sd`` ends up labelled with the new state but holds
    the prior state's data.

    Construct the mislabel scenario:
      1. Apply search 'foo' — populates filt_key_FOO with SD_foo
         (computed on 3 'foo' rows).
      2. Apply search 'bar' — populates filt_key_BAR with SD_bar
         (computed on 1 'bar' row).

    After step 2, the filt cache slot MUST hold SD_bar. If the bug
    were present, the cache lookup at step 2 would key off the prior
    state's chain (still in ``self.operations``), find filt_key_FOO,
    and assign that to ``summary_sd`` — which ``_populate_sd_cache``
    would then write under filt_key_BAR. Reading filt_key_BAR back
    would yield 3-row stats, not 1-row.
    """
    df = pd.DataFrame({'a': [10, 20, 30, 40, 50],
                       'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    dfc = _CountingDataflow(df, debug=False)

    dfc.quick_command_args = {'search': ['foo']}
    foo_rows = len(dfc.processed_df)
    assert foo_rows == 3, (
        f"precondition: search 'foo' should match 3 rows, got {foo_rows}"
    )

    dfc.quick_command_args = {'search': ['bar']}
    bar_rows = len(dfc.processed_df)
    assert bar_rows == 1, (
        f"precondition: search 'bar' should match 1 row, got {bar_rows}"
    )

    cached_filt = dfc.summary_stats_cache[dfc.filt_sd_key]
    assert cached_filt is not None
    # The processed_df has 1 row; any column-level length stat should
    # reflect that.
    saw_length_stat = False
    for col, stats in cached_filt.items():
        if 'length' in stats:
            saw_length_stat = True
            assert stats['length'] == bar_rows, (
                f"cached filt SD for column {col!r} reports length="
                f"{stats['length']}; expected {bar_rows} (current "
                f"'bar'-filtered df). A wrong length means _summary_sd "
                f"reused the prior state's cache entry."
            )
    assert saw_length_stat, (
        "precondition: at least one column should have a `length` stat"
    )
