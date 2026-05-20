"""Scoped summary stats — raw / cleaned / filtered — coexisting in merged_sd.

See docs/plans/async-stats.md for the full design. Three scopes:

- bare keys (e.g. `mean`) — computed on sampled_df (raw)
- `cleaned_*` keys — computed on the cleaned-but-unfiltered df, emitted
  only when ``cleaning_method != ""``
- `filtered_*` keys — computed on the cleaned-and-filtered df, emitted
  only when quick_command_args produces non-empty quick_ops

This is a deliberate breaking change to bare-name semantics: today
``merged_sd[col]["mean"]`` is the post-everything mean (after both
cleaning and filter). After this change it is the raw mean.
"""
import pandas as pd
import pytest

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

    # No scopes activated → no prefixed keys
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
    # No cleaning → no cleaned scope
    cleaned_keys = [k for k in sd['a'] if k.startswith('cleaned_')]
    assert cleaned_keys == [], f"unexpected cleaned_* keys: {cleaned_keys}"


def test_bare_mean_is_raw_not_filtered():
    """Deliberate breaking change: bare `mean` is the raw mean (computed on
    sampled_df), not the post-filter mean. Before this change, bare `mean`
    was the post-everything value; after, it's the pre-everything value.

    Raw `a` = [10, 20, 30, 40, 50], mean = 30.
    Filter on 'foo' keeps rows where 'b' == 'foo' → indices 0, 2, 4 →
    `a` = [10, 30, 50], filtered mean = 30. Coincidentally identical here
    by construction; the assertion that matters is that bare `mean` reflects
    the raw 5-row dataset, and that `filtered_mean` reflects the 3-row
    filtered subset. We assert via `length` (unambiguous) to keep this
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
