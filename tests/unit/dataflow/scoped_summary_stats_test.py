"""Scope-merged ``merged_sd``: bare-key raw scope + ``filtered_*`` prefixed
keys when a search filter is active. Sits on top of #783's keyed-SD cache
(``summary_stats_cache`` + ``raw_sd_key`` / ``clean_sd_key`` / ``filt_sd_key``
pointer traits).

Deliberate breaking change to bare-name semantics: today
``merged_sd[col]["mean"]`` is the post-everything mean; after this PR it is
the raw (pre-filter) mean. The post-filter value is available as
``filtered_mean`` when a filter is active.

The fourth test pre-asserts codex's P1 finding on #783 — the cache key was
derived only from the op chain, so a ``raw_df`` swap with the same chain
left stale SD blobs in the cache. The reconciled shape uses the cache as
the source of truth for bare keys, which makes that staleness directly
observable in ``merged_sd``.
"""

import pandas as pd

from typing import Any, TypedDict
from buckaroo.customizations.pandas_commands import (DropCol, FillNA, GroupBy, NoOp, SafeInt, Search)
from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf
from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2, PD_AUTOCLEAN_DEFAULT_V2, cleaning_gen_ops
from buckaroo.dataflow.autocleaning import (AutocleaningConfig, PandasAutocleaning)
from buckaroo.dataflow.dataflow import CustomizableDataflow, StylingAnalysis
from buckaroo.pluggable_analysis_framework.stat_func import stat


_AddOrigResult = TypedDict('_AddOrigResult', {'cleaning_ops': Any, 'add_orig': Any})


@stat()
def _add_orig_cleaning(int_parse: float, int_parse_fail: float) -> _AddOrigResult:
    """Auto-clean: cast numeric-looking strings via safe_int, flagging add_orig."""
    if int_parse > 0.3:
        return {'cleaning_ops': [{'symbol': 'safe_int', 'meta': {'auto_clean': True}}, {'symbol': 'df'}],
            'add_orig': True}
    return {'cleaning_ops': [], 'add_orig': False}


_AC_CLEANING = [k for k in PD_AUTOCLEAN_DEFAULT_V2 if k is not cleaning_gen_ops] + [_add_orig_cleaning]


class ScopedConf(AutocleaningConfig):
    """Cleaning + search both available."""
    autocleaning_analysis_klasses = _AC_CLEANING
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name = "default"


class ScopedDataflow(CustomizableDataflow):
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = tuple([NoCleaningConf, ScopedConf])
    analysis_klasses = [StylingAnalysis] + list(PD_ANALYSIS_V2)


def _build_dataflow():
    df = pd.DataFrame({'a': [10, 20, 30, 40, 50], 'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    return ScopedDataflow(df)


def test_no_cleaning_no_filter_only_bare_keys():
    """With neither cleaning nor filter active, merged_sd has only the raw
    scope: bare stat keys, no scope-prefixed keys."""
    dfc = _build_dataflow()
    sd = dfc.merged_sd

    assert 'a' in sd
    assert 'mean' in sd['a'], "raw scope: bare `mean` always present"

    cleaned_keys = [k for k in sd['a'] if k.startswith('cleaned_')]
    filtered_keys = [k for k in sd['a'] if k.startswith('filtered_')]
    assert cleaned_keys == [], f"unexpected cleaned_* keys: {cleaned_keys}"
    assert filtered_keys == [], f"unexpected filtered_* keys: {filtered_keys}"


def test_filter_active_emits_filtered_prefix_keys():
    """When quick_command_args produces non-empty quick_ops, merged_sd gains
    `filtered_*` keys alongside the bare raw keys."""
    dfc = _build_dataflow()
    dfc.quick_command_args = {'search': ['foo']}

    sd = dfc.merged_sd
    assert 'mean' in sd['a'], "raw scope still present"
    assert 'filtered_mean' in sd['a'], (
        "filter active: `filtered_mean` should be emitted alongside raw `mean`"
    )
    cleaned_keys = [k for k in sd['a'] if k.startswith('cleaned_')]
    assert cleaned_keys == [], f"unexpected cleaned_* keys: {cleaned_keys}"


def test_bare_mean_is_raw_not_filtered():
    """Deliberate breaking change: bare `mean` is the raw mean (computed on
    sampled_df), not the post-filter mean.

    Raw `a` = [10, 20, 30, 40, 50], length 5.
    Filter on 'foo' keeps rows where 'b' == 'foo' → indices 0, 2, 4 →
    `a` = [10, 30, 50], length 3. Asserting via `length` keeps this
    robust to mean-collision."""
    dfc = _build_dataflow()
    dfc.quick_command_args = {'search': ['foo']}

    sd = dfc.merged_sd
    assert sd['a']['length'] == 5, (
        "bare `length` should reflect the raw (pre-filter) 5-row dataset"
    )
    assert sd['a']['filtered_length'] == 3, (
        "`filtered_length` should reflect the 3-row filtered subset"
    )


def test_raw_df_change_invalidates_scoped_sd():
    """Codex P1 from #783: the cache key was derived only from the op chain,
    so a ``raw_df`` swap with the same (empty) chain reused stale entries.
    With the cache as the source of truth for bare keys, the new df's stats
    must surface in ``merged_sd``.
    """
    df1 = pd.DataFrame({'a': [10, 20, 30, 40, 50],
                        'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    df2 = pd.DataFrame({'a': [100, 200, 300, 400, 500, 600, 700],
                        'b': ['x', 'y', 'z', 'x', 'y', 'z', 'x']})
    dfc = ScopedDataflow(df1)
    assert dfc.merged_sd['a']['length'] == 5
    assert dfc.merged_sd['a']['mean'] == 30.0

    dfc.raw_df = df2
    assert dfc.merged_sd['a']['length'] == 7, (
        f"after raw_df swap, bare `length` should reflect the new 7-row "
        f"dataset; got {dfc.merged_sd['a']['length']}"
    )
    assert dfc.merged_sd['a']['mean'] == 400.0, (
        f"after raw_df swap, bare `mean` should reflect the new dataset's "
        f"mean (400.0); got {dfc.merged_sd['a']['mean']} — likely a stale "
        f"cache entry keyed only by the (unchanged) op chain"
    )


def test_cleaned_keys_appear_when_cleaning_active():
    """When ``cleaning_method`` produces auto-clean ops, the clean scope's
    SD must be layered into ``merged_sd`` with a ``cleaned_*`` prefix.

    Column 'a' is numeric-string. ``safe_int`` casts it to a UInt8 column,
    so the clean scope's ``mean`` is 30.0 (computed on ints) while the
    raw scope's ``mean`` is the string-column fallback (0).
    """
    df = pd.DataFrame({'a': ['10', '20', '30', '40', '50'],
                       'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    dfc = ScopedDataflow(df)
    dfc.cleaning_method = 'default'

    sd = dfc.merged_sd
    assert 'cleaned_mean' in sd['a'], (
        f"cleaning active: `cleaned_mean` should be emitted alongside raw "
        f"`mean`; got keys {sorted(sd['a'].keys())}"
    )
    assert sd['a']['cleaned_mean'] == 30.0, (
        f"`cleaned_mean` should be the int-cast mean (30.0); got "
        f"{sd['a']['cleaned_mean']}"
    )


def test_cleaning_only_does_not_emit_filtered_keys():
    """The pre-#785 ``filter_active`` gate was keyed on
    ``filt_sd_key != raw_sd_key``, which fires whenever the clean chain is
    non-empty — even with no search filter. The right gate is on chain
    shape: ``filtered_*`` only when ``filt`` differs from ``clean``.

    With cleaning active but no quick-command args, ``merged_sd`` must
    have ``cleaned_*`` keys and NO ``filtered_*`` keys.
    """
    df = pd.DataFrame({'a': ['10', '20', '30', '40', '50'],
                       'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    dfc = ScopedDataflow(df)
    dfc.cleaning_method = 'default'

    sd = dfc.merged_sd
    filtered_keys = [k for k in sd['a'] if k.startswith('filtered_')]
    assert filtered_keys == [], (
        f"cleaning-only state must not emit filtered_* keys; got "
        f"{filtered_keys}"
    )
    cleaned_keys = [k for k in sd['a'] if k.startswith('cleaned_')]
    assert cleaned_keys, (
        "cleaning-only state should emit cleaned_* keys; got none"
    )


def test_filter_and_clean_both_emit_correctly():
    """With both cleaning and a search filter active, ``merged_sd``
    carries bare raw keys, ``cleaned_*`` keys reflecting the clean scope,
    and ``filtered_*`` keys reflecting the filt scope. The three layers
    do not cross-talk.

    'a' is numeric-string; safe_int casts it. Search 'foo' on 'b' keeps
    the foo rows (length 4 in raw / clean scopes, with the filt scope
    nulling out non-foo rows in 'a' → 3 nulls).
    """
    df = pd.DataFrame({'a': ['10', '20', '30', '40', '50', '60', '70'],
                       'b': ['foo', 'bar', 'foo', 'baz', 'foo', 'bar', 'foo']})
    dfc = ScopedDataflow(df)
    dfc.cleaning_method = 'default'
    dfc.quick_command_args = {'search': ['foo']}

    sd = dfc.merged_sd['a']
    cleaned_keys = [k for k in sd if k.startswith('cleaned_')]
    filtered_keys = [k for k in sd if k.startswith('filtered_')]
    assert cleaned_keys, f"both-active: cleaned_* keys missing; got {sorted(sd.keys())}"
    assert filtered_keys, f"both-active: filtered_* keys missing; got {sorted(sd.keys())}"

    # Cross-talk check: the filt scope nulls out non-foo rows in 'a' (3
    # nulls), while the clean scope leaves all 7 rows intact (0 nulls).
    assert sd['cleaned_null_count'] == 0, (
        f"cleaned_null_count should reflect the clean scope (0); got "
        f"{sd['cleaned_null_count']}"
    )
    assert sd['filtered_null_count'] == 3, (
        f"filtered_null_count should reflect the filt scope (3 nulls); "
        f"got {sd['filtered_null_count']}"
    )


def test_analysis_klasses_change_invalidates_scoped_sd():
    """Codex P2 from #783: ``_scope_cache_key`` was hashed from chain +
    sampled_df + post_processing_method only. Two dataflows with the
    same df + chain but different ``analysis_klasses`` would collide on
    the same cache key, so a klass swap left stale SD blobs in the
    cache. Including ``id(analysis_klasses)`` in the cache key must
    produce distinct keys for distinct klass lists.

    Asserted at the ``_scope_cache_key`` level because ``analysis_klasses``
    is a plain class attribute (not a traitlet) on ``DataFlow`` — setting
    it on the instance doesn't fire observers, so the merged_sd-level
    behavior can't be exercised end-to-end without an unrelated
    architectural change. The cache-key contract is the load-bearing
    invariant.
    """
    df = pd.DataFrame({'a': [10, 20, 30, 40, 50],
                       'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    dfc1 = ScopedDataflow(df)
    key1 = dfc1._scope_cache_key([])

    dfc2 = ScopedDataflow(df)
    dfc2.analysis_klasses = list(PD_ANALYSIS_V2)
    key2 = dfc2._scope_cache_key([])

    assert key1 != key2, (
        f"scope cache key must differ when analysis_klasses differs; "
        f"got the same key {key1} for both — likely the cache key still "
        f"omits analysis_klasses identity (Codex P2)"
    )
