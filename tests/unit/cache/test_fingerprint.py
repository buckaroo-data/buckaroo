"""Tests for the initial-load cache config fingerprint.

config_fingerprint produces a stable, cross-process identifier of the
*data-touching* configuration (analysis klasses, sampling, init_sd,
skip columns, version). It is the key the handshake validates: a bundle
whose config_fingerprint matches the widget's live config is safe to use
without recomputing.
"""
import subprocess
import sys

from buckaroo.cache.fingerprint import config_fingerprint, INITIAL_CACHE_VERSION
from buckaroo.customizations.analysis import TypingStats, DefaultSummaryStats
from buckaroo.customizations.histogram import Histogram


def test_deterministic_and_hexish():
    a = config_fingerprint(analysis_klasses=[TypingStats, DefaultSummaryStats])
    b = config_fingerprint(analysis_klasses=[TypingStats, DefaultSummaryStats])
    assert a == b
    assert isinstance(a, str) and len(a) >= 8
    int(a, 16)  # hex digest


def test_membership_changes_fingerprint():
    one = config_fingerprint(analysis_klasses=[TypingStats])
    two = config_fingerprint(analysis_klasses=[TypingStats, DefaultSummaryStats])
    three = config_fingerprint(analysis_klasses=[TypingStats, DefaultSummaryStats, Histogram])
    assert len({one, two, three}) == 3


def test_version_changes_fingerprint():
    base = config_fingerprint(analysis_klasses=[TypingStats])
    assert config_fingerprint(analysis_klasses=[TypingStats], cache_version="v2") != base


def test_init_sd_and_skip_columns_change_fingerprint():
    base = config_fingerprint(analysis_klasses=[TypingStats])
    assert config_fingerprint(
        analysis_klasses=[TypingStats], init_sd={'a': {'mean': 1}}) != base
    assert config_fingerprint(
        analysis_klasses=[TypingStats], skip_stat_columns=['a']) != base


def test_skip_columns_order_insensitive():
    # skip_stat_columns is a set of column names; order must not matter.
    x = config_fingerprint(analysis_klasses=[TypingStats], skip_stat_columns=['a', 'b'])
    y = config_fingerprint(analysis_klasses=[TypingStats], skip_stat_columns=['b', 'a'])
    assert x == y


def test_stable_across_processes():
    # The whole point: a bundle built in one process must validate in another.
    # An id()-based key would fail this; a qualname-based one passes.
    code = (
        "from buckaroo.cache.fingerprint import config_fingerprint;"
        "from buckaroo.customizations.analysis import TypingStats, DefaultSummaryStats;"
        "print(config_fingerprint(analysis_klasses=[TypingStats, DefaultSummaryStats]))")
    out = subprocess.check_output([sys.executable, "-c", code]).decode().strip()
    assert out == config_fingerprint(analysis_klasses=[TypingStats, DefaultSummaryStats])


def test_version_constant_is_int():
    assert isinstance(INITIAL_CACHE_VERSION, int)
