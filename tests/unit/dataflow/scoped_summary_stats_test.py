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

from buckaroo.customizations.analysis import DefaultSummaryStats, PdCleaningStats
from buckaroo.customizations.pandas_commands import (DropCol, FillNA, GroupBy, NoOp, SafeInt, Search)
from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf
from buckaroo.dataflow.autocleaning import (AutocleaningConfig, PandasAutocleaning)
from buckaroo.dataflow.dataflow import CustomizableDataflow, StylingAnalysis
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis


class CleaningGenOps(ColAnalysis):
    """Auto-clean: cast numeric-looking strings via safe_int."""
    requires_summary = ['int_parse_fail', 'int_parse']
    provides_defaults = {'cleaning_ops': []}
    int_parse_threshhold = .3

    @classmethod
    def computed_summary(kls, column_metadata):
        if column_metadata['int_parse'] > kls.int_parse_threshhold:
            return {
                'cleaning_ops': [{'symbol': 'safe_int',
                                  'meta': {'auto_clean': True}},
                                 {'symbol': 'df'}],
                'add_orig': True,
            }
        return {'cleaning_ops': []}


class ScopedConf(AutocleaningConfig):
    """Cleaning + search both available."""
    autocleaning_analysis_klasses = [DefaultSummaryStats, CleaningGenOps, PdCleaningStats]
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name = "default"


class ScopedDataflow(CustomizableDataflow):
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = tuple([NoCleaningConf, ScopedConf])
    analysis_klasses = [StylingAnalysis, DefaultSummaryStats]


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


def test_cleaning_only_does_not_emit_filtered_keys():
    """Cleaning ops in the chain (but no search/quick-command) must NOT
    cause ``filtered_*`` keys to appear. ``filtered_*`` semantically means
    "search filter is active"; a key-inequality gate (filt_sd_key !=
    raw_sd_key) would mislabel cleaning-affected stats as filtered until
    the deferred ``cleaned_*`` scope lands. The gate must be on the
    chains themselves: filt != clean.
    """
    df = pd.DataFrame({'a': ['10', '20', '30', '40', '50'],
                       'b': ['foo', 'bar', 'foo', 'baz', 'foo']})
    dfc = ScopedDataflow(df)
    dfc.cleaning_method = 'default'

    clean_chain = [op for op in (dfc.operations or [])
                   if isinstance(op, list) and len(op) > 0]
    assert len(clean_chain) > 0, (
        "precondition: cleaning_method='default' should have produced "
        "cleaning ops for a numeric-string column"
    )

    sd = dfc.merged_sd
    filtered_keys = [k for k in sd.get('a', {}) if k.startswith('filtered_')]
    assert filtered_keys == [], (
        f"cleaning-only state must not emit filtered_* keys; got "
        f"{filtered_keys}. The `filter_active` gate is firing on "
        f"filt_sd_key != raw_sd_key instead of on the chain-shape "
        f"difference between filt and clean."
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
