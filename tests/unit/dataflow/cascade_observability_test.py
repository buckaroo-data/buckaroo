"""Tests for cascade observability — issue #822.

The dataflow cascade (``_operation_result`` → ``cleaned`` →
``_processed_result`` → ``_summary_sd`` → ``_merged_sd`` →
``_populate_sd_cache``) is the hot path for every state_change. We want
one log line per observer per fire, with elapsed_ms, the trait change
that triggered it, and a per-cascade correlation id, on a dedicated
``buckaroo.dataflow.cache_timing`` channel at DEBUG level.

These tests assert the observability surface, not cascade behavior —
they only inspect ``caplog`` records on the cache_timing channel.
"""
import logging
import re

import pandas as pd
import pytest

from buckaroo import BuckarooWidget
from buckaroo.customizations.analysis import DefaultSummaryStats, PdCleaningStats
from buckaroo.customizations.pandas_commands import (
    DropCol, FillNA, GroupBy, NoOp, SafeInt, Search)
from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf
from buckaroo.dataflow.autocleaning import AutocleaningConfig, PandasAutocleaning
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis


CACHE_TIMING_CHANNEL = "buckaroo.dataflow.cache_timing"

# Observers covered by the cascade observability layer. Every member of
# this set must emit at least one log line during a normal state_change
# cycle.
CASCADE_OBSERVERS = {'_sampled_df', '_operation_result', '_processed_result', '_summary_sd', '_merged_sd',
    '_populate_sd_cache', '_widget_config', '_handle_widget_change'}

# Match the per-step log format. Keep the regex strict so format drift
# trips a test rather than silently degrading the log channel.
LINE_RE = re.compile(
    r'^cascade '
    r'cid=(?P<cid>\d+) '
    r'observer=(?P<observer>[A-Za-z_][A-Za-z0-9_]*) '
    r'trait=(?P<trait>[A-Za-z_][A-Za-z0-9_]*) '
    r'elapsed_ms=(?P<elapsed>\d+\.\d+)$')


class _CleaningGenOps(ColAnalysis):
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
    autocleaning_analysis_klasses = [DefaultSummaryStats, _CleaningGenOps, PdCleaningStats]
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name = 'default'


class _CascadeWidget(BuckarooWidget):
    autocleaning_klass = PandasAutocleaning
    autoclean_conf = (_Conf, NoCleaningConf)


@pytest.fixture
def dirty_df():
    return pd.DataFrame({'a': [10, 20, 30, 40, 10, 20.3, 5, None, None, None],
        'b': ['3', '4', 'a', '5', '5', 'b', 'b', None, None, None]})


def _parse_lines(records):
    parsed = []
    for rec in records:
        if rec.name != CACHE_TIMING_CHANNEL:
            continue
        m = LINE_RE.match(rec.getMessage())
        assert m is not None, (
            f"cache_timing log line does not match expected format: {rec.getMessage()!r}"
        )
        parsed.append({'cid': int(m.group('cid')), 'observer': m.group('observer'), 'trait': m.group('trait'),
            'elapsed_ms': float(m.group('elapsed')), 'level': rec.levelname})
    return parsed


def test_cache_timing_channel_emits_at_debug_level(dirty_df, caplog):
    """All cache_timing log lines should be DEBUG level (channel must
    not flood at INFO during normal operation)."""
    with caplog.at_level(logging.DEBUG, logger=CACHE_TIMING_CHANNEL):
        bw = _CascadeWidget(dirty_df, debug=False)
        bw.buckaroo_state = {**bw.buckaroo_state, 'quick_command_args': {'search': ['needle']}}

    parsed = _parse_lines(caplog.records)
    assert parsed, "expected cache_timing log lines but got none"
    assert all(p['level'] == 'DEBUG' for p in parsed), (
        f"all cache_timing lines must be DEBUG, got levels "
        f"{sorted({p['level'] for p in parsed})}"
    )


def test_cache_timing_channel_silent_at_info_level(dirty_df, caplog):
    """The cache_timing channel must not emit at INFO — it would flood
    normal widget operation otherwise."""
    with caplog.at_level(logging.INFO, logger=CACHE_TIMING_CHANNEL):
        _CascadeWidget(dirty_df, debug=False)

    info_lines = [r for r in caplog.records
                  if r.name == CACHE_TIMING_CHANNEL and r.levelno >= logging.INFO]
    assert info_lines == [], (
        f"cache_timing channel emitted at INFO+: {[r.getMessage() for r in info_lines]}"
    )


def test_every_cascade_observer_logs_during_state_change(dirty_df, caplog):
    """Each cascade observer must emit at least one cache_timing line
    during a state_change cycle."""
    with caplog.at_level(logging.DEBUG, logger=CACHE_TIMING_CHANNEL):
        bw = _CascadeWidget(dirty_df, debug=False)
        # A filter flip exercises the full cascade.
        bw.buckaroo_state = {**bw.buckaroo_state, 'quick_command_args': {'search': ['needle']}}

    parsed = _parse_lines(caplog.records)
    observers_seen = {p['observer'] for p in parsed}
    missing = CASCADE_OBSERVERS - observers_seen
    assert not missing, (
        f"cascade observers missing cache_timing coverage: {sorted(missing)}; "
        f"saw {sorted(observers_seen)}"
    )


def test_one_cascade_shares_one_correlation_id(dirty_df, caplog):
    """A single ``buckaroo_state`` flip triggers one cascade — every log
    line emitted by it must share the same correlation id."""
    # Build the widget first so its construction cascade is excluded
    # from the assertion.
    bw = _CascadeWidget(dirty_df, debug=False)

    with caplog.at_level(logging.DEBUG, logger=CACHE_TIMING_CHANNEL):
        bw.buckaroo_state = {**bw.buckaroo_state, 'quick_command_args': {'search': ['needle']}}

    parsed = _parse_lines(caplog.records)
    assert parsed, "expected cascade log lines for the state flip"

    cids = {p['cid'] for p in parsed}
    # The buckaroo_state change can drive at most a single cascade per
    # top-level set on the dataflow (post_processing / cleaning_method /
    # quick_command_args). We're flipping only quick_command_args so the
    # cascade is a single rooted tree — one correlation id.
    assert len(cids) == 1, (
        f"one cascade should share one correlation id, got cids={sorted(cids)} "
        f"across observers={sorted({p['observer'] for p in parsed})}"
    )


def test_correlation_id_is_monotonic(dirty_df, caplog):
    """Successive cascades must mint strictly-increasing correlation
    ids — otherwise observers from different cascades collide in the
    logs."""
    bw = _CascadeWidget(dirty_df, debug=False)

    with caplog.at_level(logging.DEBUG, logger=CACHE_TIMING_CHANNEL):
        bw.buckaroo_state = {**bw.buckaroo_state, 'quick_command_args': {'search': ['n1']}}
        first_cycle = _parse_lines(caplog.records)
        caplog.clear()
        bw.buckaroo_state = {**bw.buckaroo_state, 'quick_command_args': {'search': ['n2']}}
        second_cycle = _parse_lines(caplog.records)

    assert first_cycle and second_cycle, "both cycles must produce log lines"
    max_first = max(p['cid'] for p in first_cycle)
    min_second = min(p['cid'] for p in second_cycle)
    assert min_second > max_first, (
        f"correlation ids must increase across cascades — "
        f"first max={max_first}, second min={min_second}"
    )


def test_log_format_is_uniform(dirty_df, caplog):
    """Every cache_timing line must match the documented format —
    cascade cid=<int> observer=<name> trait=<name> elapsed_ms=<float>."""
    with caplog.at_level(logging.DEBUG, logger=CACHE_TIMING_CHANNEL):
        _CascadeWidget(dirty_df, debug=False)

    records = [r for r in caplog.records if r.name == CACHE_TIMING_CHANNEL]
    assert records, "expected cache_timing records"
    for rec in records:
        msg = rec.getMessage()
        assert LINE_RE.match(msg), (
            f"cache_timing line does not match documented format: {msg!r}"
        )
