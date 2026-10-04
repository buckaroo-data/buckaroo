"""Unit tests for ``buckaroo.server.stats_policy`` (rows-first p31, p31b).

Everything here is pure Python: the policy is a function of numbers, the
probes read a schema or a parquet footer, and nothing needs a server. The last
sections (rows-first p33) test how the session carries the result and how
``df_meta.stats`` reports it, still without a server; the HTTP and WebSocket
side is in test_load_expr.py. The last section (rows-first p37) tests the
guards for huge sources: the sort and search thresholds, the flags a session
reports, the refusal of a sorted window, and the pass that turns sorting off in a
display config.

The thresholds are the provisional values proposed by the phase-0
measurements (p31b). The boundary tables run on the module defaults, so a
change to a ``DEFAULT_*`` constant fails them and the table is updated
together with the constant. ``TestCalibratedDefaults`` pins each default to
its literal value.
"""
import dataclasses
import importlib
import importlib.util
import io
import json
import logging
from types import SimpleNamespace

import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from buckaroo.server import session as session_mod
from buckaroo.server import stats_wire

ENV_FIELDS = {"BUCKAROO_STATS_FULL_AUTO_ROWS": "full_auto_rows", "BUCKAROO_STATS_FULL_AUTO_CELLS": "full_auto_cells",
    "BUCKAROO_STATS_SCALAR_AUTO_CELLS": "scalar_auto_cells", "BUCKAROO_STATS_CEILING_FULL_ROWS": "ceiling_full_rows",
    "BUCKAROO_STATS_CEILING_FULL_CELLS": "ceiling_full_cells",
    "BUCKAROO_STATS_CEILING_SCALAR_CELLS": "ceiling_scalar_cells", "BUCKAROO_POLARS_ROUTE_ROWS": "polars_route_rows"}

# The phase-0 values (measurements-phase0.md, "Proposed values"), written out
# so a change to a module default has to change a test too.
CALIBRATED = {"full_auto_rows": 12_000_000, "full_auto_cells": 520_000_000, "scalar_auto_cells": 1_000_000_000,
    "ceiling_full_rows": 25_000_000, "ceiling_full_cells": 1_000_000_000, "ceiling_scalar_cells": 4_000_000_000,
    "polars_route_rows": 8_000_000}
CALIBRATED_CONSTANTS = {"DEFAULT_FULL_AUTO_ROWS": 12_000_000, "DEFAULT_FULL_AUTO_CELLS": 520_000_000,
    "DEFAULT_SCALAR_AUTO_CELLS": 1_000_000_000, "DEFAULT_CEILING_FULL_ROWS": 25_000_000,
    "DEFAULT_CEILING_FULL_CELLS": 1_000_000_000, "DEFAULT_CEILING_SCALAR_CELLS": 4_000_000_000,
    "DEFAULT_POLARS_ROUTE_ROWS": 8_000_000}

TIER_RANK = {"schema": 0, "scalar": 1, "full": 2}


@pytest.fixture
def sp():
    spec = importlib.util.find_spec("buckaroo.server.stats_policy")
    assert spec is not None, "buckaroo.server.stats_policy is not importable"
    return importlib.import_module("buckaroo.server.stats_policy")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """A developer's own BUCKAROO_STATS_* overrides must not leak in."""
    for name in ENV_FIELDS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def lim(sp):
    """The module defaults. The tables are written against the calibrated
    values, so moving a ``DEFAULT_*`` constant fails them."""
    return sp.StatsLimits()


def _resolve(sp, lim, backend, source_kind, rows, cols, host_tier=None, bytes=None):
    return sp.resolve_stats_policy(
        backend, source_kind, rows, cols, bytes=bytes, host_tier=host_tier, limits=lim)


# (backend, source_kind, rows, cols, host_tier) -> (tier_target, auto_request,
# requestable, reason). The row counts of 42.3M, 54.1M and 78.0M and the 44
# columns are the three tallyman entries over 70 s; 10.8M x 43 is parking_2017.
# Each threshold has an equal, a one-below and a one-above row, in rows and,
# where the rule reads cells, in cells (a row count or a column count moves
# the product). The comments give the cell count where it decides the row.
RESOLVE_TABLE = [
    # Eager backends resolve to full and ignore the host tier and the cell bounds.
    ("pandas", "memory", 52_814, 27, None, ("full", True, [], None)),
    ("pandas", "parquet", 1_000_000, 43, None, ("full", True, [], None)),
    ("polars", "parquet", 10_800_000, 43, None, ("full", True, [], None)),
    ("polars", "parquet", 10_800_000, 43, "schema", ("full", True, [], None)),
    ("pandas", "csv", 52_814, 27, "scalar", ("full", True, [], None)),
    ("pandas", "memory", 30_000_000, 100, None, ("full", True, [], None)),
    # xorq sized by the policy alone: full up to 12M rows.
    ("xorq", "parquet", 0, 0, None, ("full", True, [], None)),
    ("xorq", "parquet", 52_814, 27, None, ("full", True, [], None)),
    ("xorq", "parquet", 10_800_000, 43, None, ("full", True, [], None)),
    ("xorq", "parquet", 11_999_999, 43, None, ("full", True, [], None)),
    ("xorq", "parquet", 12_000_000, 43, None, ("full", True, [], None)),
    ("xorq", "parquet", 12_000_001, 43, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 12_000_000, 10, None, ("full", True, [], None)),
    ("xorq", "parquet", 12_000_001, 10, None, ("scalar", True, ["full"], "size")),
    # The 11.7M-row CSV entries: 515.8M cells at 44 columns, 527.5M at 45.
    ("xorq", "csv", 11_721_603, 44, None, ("full", True, [], None)),
    ("xorq", "csv", 11_721_603, 45, None, ("scalar", True, ["full"], "size")),
    # full auto also stops at 520M cells, reached by rows or by columns.
    ("xorq", "parquet", 9_999_999, 52, None, ("full", True, [], None)),
    ("xorq", "parquet", 10_000_000, 52, None, ("full", True, [], None)),
    ("xorq", "parquet", 10_000_001, 52, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 8_000_000, 65, None, ("full", True, [], None)),
    ("xorq", "parquet", 8_000_000, 66, None, ("scalar", True, ["full"], "size")),
    # scalar auto up to 1.0B cells; full stays requestable up to its own ceiling.
    ("xorq", "parquet", 11_000_000, 90, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 11_000_000, 100, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "parquet", 19_999_999, 50, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 20_000_000, 50, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 20_000_001, 50, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "parquet", 22_727_272, 44, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 22_727_273, 44, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "parquet", 12_500_000, 80, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 12_500_000, 81, None, ("schema", False, ["scalar"], "size")),
    # The three slow tallyman entries are above 1.8B cells and start at schema.
    ("xorq", "csv", 42_300_000, 44, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "csv", 50_000_000, 44, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "csv", 54_100_000, 44, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "csv", 78_000_000, 44, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "csv", 78_000_000, 44, "auto", ("schema", False, ["scalar"], "size")),
    # Past the scalar ceiling (4.0B cells) nothing is requestable.
    ("xorq", "csv", 100_000_000, 40, None, ("schema", False, ["scalar"], "size")),
    ("xorq", "csv", 100_000_001, 40, None, ("schema", False, [], "size")),
    # The host lowers freely.
    ("xorq", "parquet", 1_000_000, 43, "schema", ("schema", False, ["scalar", "full"], "host")),
    ("xorq", "parquet", 1_000_000, 43, "scalar", ("scalar", True, ["full"], "host")),
    ("xorq", "parquet", 1_000_000, 43, "full", ("full", True, [], None)),
    # The host raises only as far as the ceiling on full: 25M rows ...
    ("xorq", "parquet", 12_000_000, 43, "full", ("full", True, [], None)),
    ("xorq", "parquet", 24_999_999, 10, "full", ("full", True, [], None)),
    ("xorq", "parquet", 25_000_000, 10, "full", ("full", True, [], None)),
    ("xorq", "parquet", 25_000_001, 10, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "parquet", 25_000_000, 10, None, ("scalar", True, ["full"], "size")),
    ("xorq", "parquet", 25_000_001, 10, None, ("scalar", True, [], "size")),
    # ... or 1.0B cells, reached by rows or by columns.
    ("xorq", "parquet", 24_999_999, 40, "full", ("full", True, [], None)),
    ("xorq", "parquet", 25_000_000, 40, "full", ("full", True, [], None)),
    ("xorq", "parquet", 25_000_000, 41, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "parquet", 20_000_000, 50, "full", ("full", True, [], None)),
    ("xorq", "parquet", 20_000_001, 50, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "parquet", 11_000_000, 90, "full", ("full", True, [], None)),
    ("xorq", "parquet", 11_000_000, 91, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "csv", 42_300_000, 44, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "csv", 50_000_000, 44, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "csv", 50_000_001, 44, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "csv", 78_000_000, 44, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "csv", 78_000_000, 44, "scalar", ("scalar", True, [], "host")),
    ("xorq", "csv", 78_000_000, 44, "schema", ("schema", False, ["scalar"], "host")),
    # The ceiling on scalar is 4.0B cells, reached by rows or by columns.
    ("xorq", "csv", 99_999_999, 40, "scalar", ("scalar", True, [], "host")),
    ("xorq", "csv", 100_000_000, 40, "scalar", ("scalar", True, [], "host")),
    ("xorq", "csv", 100_000_001, 40, "scalar", ("schema", False, [], "ceiling")),
    ("xorq", "csv", 50_000_000, 80, "scalar", ("scalar", True, [], "host")),
    ("xorq", "csv", 50_000_000, 81, "scalar", ("schema", False, [], "ceiling")),
    ("xorq", "csv", 100_000_000, 40, "full", ("scalar", True, [], "ceiling")),
    ("xorq", "csv", 100_000_001, 40, "full", ("schema", False, [], "ceiling")),
    ("xorq", "csv", 100_000_001, 40, "schema", ("schema", False, [], "host")),
]


def _table_id(case):
    backend, _kind, rows, cols, host_tier, _expected = case
    return f"{backend}-{rows}x{cols}-{host_tier}"


class TestResolveStatsPolicy:
    @pytest.mark.parametrize(
        "backend, source_kind, rows, cols, host_tier, expected", RESOLVE_TABLE,
        ids=[_table_id(c) for c in RESOLVE_TABLE])
    def test_table(self, sp, lim, backend, source_kind, rows, cols, host_tier, expected):
        out = _resolve(sp, lim, backend, source_kind, rows, cols, host_tier)
        got = (out["tier_target"], out["auto_request"], out["requestable"], out["reason"])
        assert got == expected

    def test_result_has_exactly_the_planned_keys(self, sp, lim):
        out = _resolve(sp, lim, "xorq", "parquet", 12_400_000, 43)
        assert set(out) == {"tier_target", "auto_request", "requestable", "reason", "estimate"}

    def test_result_is_json_serialisable(self, sp, lim):
        """It becomes df_meta.stats, so it has to survive json.dumps."""
        out = _resolve(sp, lim, "xorq", "csv", 78_000_000, 44, "full")
        assert json.loads(json.dumps(out)) == out

    def test_estimate_reports_the_inputs(self, sp, lim):
        out = _resolve(sp, lim, "xorq", "parquet", 12_400_000, 43)
        assert out["estimate"] == {"rows": 12_400_000, "cols": 43}

    def test_estimate_includes_bytes_when_given(self, sp, lim):
        out = _resolve(sp, lim, "xorq", "parquet", 12_400_000, 43, bytes=987_654_321)
        assert out["estimate"] == {"rows": 12_400_000, "cols": 43, "bytes": 987_654_321}

    def test_numpy_integer_counts_are_accepted(self, sp, lim):
        out = _resolve(sp, lim, "xorq", "parquet", np.int64(13_000_000), np.int64(43))
        assert out["tier_target"] == "scalar"
        assert out["estimate"] == {"rows": 13_000_000, "cols": 43}

    @pytest.mark.parametrize("rows, cols", [(-1, 3), (3, -1), (None, 3), (3, None), (1.5, 3)])
    def test_bad_counts_are_rejected(self, sp, lim, rows, cols):
        with pytest.raises((TypeError, ValueError)):
            _resolve(sp, lim, "xorq", "parquet", rows, cols)

    def test_numpy_integer_bytes_are_echoed_as_plain_ints(self, sp, lim):
        """df.memory_usage(deep=True).sum() is a np.int64, and the result has
        to survive json.dumps."""
        out = _resolve(sp, lim, "xorq", "parquet", 12_400_000, 43, bytes=np.int64(987_654_321))
        assert type(out["estimate"]["bytes"]) is int
        assert json.loads(json.dumps(out)) == out

    @pytest.mark.parametrize("bad", [-1, "lots", 1.5, object()])
    def test_bad_bytes_are_rejected(self, sp, lim, bad):
        with pytest.raises((TypeError, ValueError)):
            _resolve(sp, lim, "xorq", "parquet", 12_400_000, 43, bytes=bad)

    def test_a_host_tier_in_the_bytes_slot_is_rejected(self, sp):
        """bytes sits before host_tier, so a positional slip must not be taken
        for a byte count."""
        with pytest.raises((TypeError, ValueError)):
            sp.resolve_stats_policy("xorq", "csv", 12_000_000, 43, "full")

    @pytest.mark.parametrize("bad", [None, 5, b"csv"])
    def test_bad_source_kind_is_rejected(self, sp, lim, bad):
        with pytest.raises(TypeError):
            _resolve(sp, lim, "xorq", bad, 1_000, 3)

    def test_unknown_host_tier_is_rejected(self, sp, lim):
        with pytest.raises(ValueError):
            _resolve(sp, lim, "xorq", "parquet", 1_000, 3, "everything")

    def test_unknown_host_tier_is_rejected_for_eager_backends_too(self, sp, lim):
        with pytest.raises(ValueError):
            _resolve(sp, lim, "pandas", "memory", 1_000, 3, "everything")

    def test_defaults_refuse_full_for_the_78m_row_entry(self, sp):
        """No calibration may let a host request full on the 215 s entry."""
        out = sp.resolve_stats_policy("xorq", "csv", 78_000_000, 44, host_tier="full")
        assert TIER_RANK[out["tier_target"]] < TIER_RANK["full"]
        assert out["reason"] == "ceiling"
        assert "full" not in out["requestable"]

    def test_defaults_let_the_control_recover_parking_2017(self, sp):
        """10.8M x 43 columns took 3.7 s of stats and was fine, so a default
        that withholds it must offer full on demand."""
        out = sp.resolve_stats_policy("xorq", "parquet", 10_800_000, 43)
        assert out["tier_target"] == "full" or "full" in out["requestable"]


class TestCalibratedDefaults:
    """The module defaults are the phase-0 proposals, one literal per value."""

    def test_limits_defaults(self, sp):
        assert dataclasses.asdict(sp.StatsLimits()) == CALIBRATED

    def test_module_constants(self, sp):
        assert {name: getattr(sp, name, None) for name in CALIBRATED_CONSTANTS} == CALIBRATED_CONSTANTS

    def test_from_env_with_a_clean_environment_is_the_calibrated_set(self, sp):
        assert dataclasses.asdict(sp.StatsLimits.from_env()) == CALIBRATED

    def test_every_limit_has_an_environment_override(self, sp):
        """A new limit without an override could not be tuned on a server."""
        assert set(ENV_FIELDS.values()) == {f.name for f in dataclasses.fields(sp.StatsLimits)}


class TestCeiling:
    """The ceiling is applied inside the function, so every caller gets it:
    load, /reload_expr and a stats_request {force} all end in this call."""

    HOST_TIERS = [None, "auto", "schema", "scalar", "full"]

    def test_host_full_above_the_ceiling_resolves_lower(self, sp, lim):
        out = _resolve(sp, lim, "xorq", "csv", 78_000_000, 44, "full")
        assert out["tier_target"] == "scalar"
        assert out["reason"] == "ceiling"

    def test_reload_re_resolves_against_the_new_row_count(self, sp, lim):
        """/reload_expr keeps the stored host tier and re-resolves. An entry
        that fit under the ceiling and then grew past it loses full."""
        before = _resolve(sp, lim, "xorq", "parquet", 20_000_000, 44, "full")
        assert before["tier_target"] == "full"
        after = _resolve(sp, lim, "xorq", "parquet", 78_000_000, 44, "full")
        assert after["tier_target"] == "scalar"
        assert after["reason"] == "ceiling"

    def test_force_cannot_exceed_the_ceiling(self, sp, lim):
        """A force request passes the requested tier as host_tier."""
        loaded = _resolve(sp, lim, "xorq", "csv", 78_000_000, 44)
        assert loaded["tier_target"] == "schema"
        assert "full" not in loaded["requestable"]
        forced = _resolve(sp, lim, "xorq", "csv", 78_000_000, 44, "full")
        assert TIER_RANK[forced["tier_target"]] < TIER_RANK["full"]
        assert forced["reason"] == "ceiling"

    def test_ceiling_applies_to_the_automatic_choice_too(self, sp):
        """A server whose ceiling sits below its own auto threshold is
        clamped, with no host tier involved."""
        lim = sp.StatsLimits(full_auto_rows=10_000_000, ceiling_full_rows=5_000_000)
        out = sp.resolve_stats_policy("xorq", "parquet", 7_000_000, 10, limits=lim)
        assert out["tier_target"] == "scalar"
        assert out["reason"] == "ceiling"

    def test_scalar_ceiling_can_leave_nothing_requestable(self, sp):
        lim = sp.StatsLimits(ceiling_full_rows=50_000_000, ceiling_scalar_cells=1_000_000_000)
        out = sp.resolve_stats_policy("xorq", "csv", 78_000_000, 44, host_tier="full", limits=lim)
        assert out["tier_target"] == "schema"
        assert out["reason"] == "ceiling"
        assert out["auto_request"] is False
        assert out["requestable"] == []

    def test_scalar_ceiling_does_not_touch_smaller_entries(self, sp):
        lim = sp.StatsLimits(ceiling_full_rows=50_000_000, ceiling_scalar_cells=1_000_000_000)
        out = sp.resolve_stats_policy("xorq", "parquet", 1_000_000, 44, host_tier="full", limits=lim)
        assert out["tier_target"] == "full"

    @pytest.mark.parametrize("rows",
        [0, 1_000, 10_000_000, 11_000_000, 50_000_000, 50_000_001, 78_000_000, 500_000_000])
    @pytest.mark.parametrize("cols", [1, 44])
    @pytest.mark.parametrize("host_tier", HOST_TIERS)
    def test_full_never_resolves_above_the_ceiling(self, sp, lim, rows, cols, host_tier):
        out = _resolve(sp, lim, "xorq", "parquet", rows, cols, host_tier)
        if rows > lim.ceiling_full_rows:
            assert out["tier_target"] != "full"
            assert "full" not in out["requestable"]

    @pytest.mark.parametrize("rows", [1_000, 10_800_000, 42_300_000, 50_000_001, 78_000_000])
    def test_requestable_is_exactly_what_a_force_would_grant(self, sp, lim, rows):
        """Every tier the result offers is granted when asked for, and every
        tier above the target that it does not offer is clipped."""
        out = _resolve(sp, lim, "xorq", "parquet", rows, 44)
        for tier in ("scalar", "full"):
            if TIER_RANK[tier] <= TIER_RANK[out["tier_target"]]:
                continue
            forced = _resolve(sp, lim, "xorq", "parquet", rows, 44, tier)
            if tier in out["requestable"]:
                assert forced["tier_target"] == tier
            else:
                assert forced["tier_target"] != tier
                assert forced["reason"] == "ceiling"


    @pytest.mark.parametrize("rows, cols",
        [(20_000_001, 50), (25_000_000, 41), (11_000_000, 91), (24_999_999, 41), (42_300_000, 44), (78_000_000, 44)])
    @pytest.mark.parametrize("host_tier", HOST_TIERS)
    def test_full_never_resolves_above_the_cell_ceiling(self, sp, lim, rows, cols, host_tier):
        """1.0B cells, whatever the row count and the host asks for."""
        assert rows * cols > 1_000_000_000
        out = _resolve(sp, lim, "xorq", "parquet", rows, cols, host_tier)
        assert out["tier_target"] != "full"
        assert "full" not in out["requestable"]

    @pytest.mark.parametrize("rows, cols",
        [(25_000_001, 10), (25_000_001, 1), (30_000_000, 5), (42_300_000, 4), (78_000_000, 1)])
    @pytest.mark.parametrize("host_tier", HOST_TIERS)
    def test_full_never_resolves_above_25m_rows_however_few_the_cells(self, sp, lim, rows, cols, host_tier):
        """The row ceiling holds on its own: these entries are under 1.0B cells."""
        assert rows * cols < 1_000_000_000
        out = _resolve(sp, lim, "xorq", "parquet", rows, cols, host_tier)
        assert out["tier_target"] != "full"
        assert "full" not in out["requestable"]

    @pytest.mark.parametrize("rows, cols",
        [(100_000_001, 40), (50_000_000, 81), (1_000_000, 4_001), (500_000_000, 10)])
    @pytest.mark.parametrize("host_tier", HOST_TIERS)
    def test_nothing_above_the_scalar_ceiling_resolves_past_schema(self, sp, lim, rows, cols, host_tier):
        """4.0B cells, the placeholder scalar ceiling."""
        assert rows * cols > 4_000_000_000
        out = _resolve(sp, lim, "xorq", "parquet", rows, cols, host_tier)
        assert out["tier_target"] == "schema"
        assert out["requestable"] == []

    def test_a_scalar_ceiling_is_on_by_default(self, sp):
        out = sp.resolve_stats_policy("xorq", "csv", 100_000_001, 40, host_tier="scalar", limits=sp.StatsLimits())
        assert out["tier_target"] == "schema"
        assert out["reason"] == "ceiling"


    @pytest.mark.parametrize("rows, cols",
        [(12_000_001, 43), (10_000_001, 52), (11_000_000, 91), (20_000_000, 50), (20_000_001, 50), (22_727_273, 44),
         (25_000_000, 40), (25_000_000, 41), (25_000_001, 10), (50_000_000, 81), (100_000_000, 40),
         (100_000_001, 40)])
    def test_requestable_matches_a_force_at_the_row_and_cell_boundaries(self, sp, lim, rows, cols):
        """With the cell bounds, the tiers a result offers are still exactly
        the ones a force request is granted."""
        out = _resolve(sp, lim, "xorq", "parquet", rows, cols)
        for tier in ("scalar", "full"):
            if TIER_RANK[tier] <= TIER_RANK[out["tier_target"]]:
                continue
            forced = _resolve(sp, lim, "xorq", "parquet", rows, cols, tier)
            if tier in out["requestable"]:
                assert forced["tier_target"] == tier
            else:
                assert forced["tier_target"] != tier
                assert forced["reason"] == "ceiling"


class TestLimitsFromEnv:
    def test_defaults_when_the_environment_is_empty(self, sp):
        assert sp.StatsLimits.from_env() == sp.StatsLimits()

    @pytest.mark.parametrize("name, field", ENV_FIELDS.items())
    def test_each_variable_overrides_its_field(self, sp, monkeypatch, name, field):
        monkeypatch.setenv(name, "12345")
        assert getattr(sp.StatsLimits.from_env(), field) == 12345

    def test_underscored_integers_are_accepted(self, sp, monkeypatch):
        monkeypatch.setenv("BUCKAROO_STATS_FULL_AUTO_ROWS", "2_000_000")
        assert sp.StatsLimits.from_env().full_auto_rows == 2_000_000

    @pytest.mark.parametrize("name, field", ENV_FIELDS.items())
    @pytest.mark.parametrize("bad", ["lots", "-5", "1.5"])
    def test_invalid_value_falls_back_to_the_default_and_warns(self, sp, monkeypatch, caplog, name, field, bad):
        monkeypatch.setenv(name, bad)
        with caplog.at_level(logging.WARNING):
            limits = sp.StatsLimits.from_env()
        assert getattr(limits, field) == getattr(sp.StatsLimits(), field)
        assert name in caplog.text

    def test_empty_value_means_unset(self, sp, monkeypatch):
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_SCALAR_CELLS", "")
        assert sp.StatsLimits.from_env().ceiling_scalar_cells == sp.StatsLimits().ceiling_scalar_cells

    def test_resolve_reads_the_environment_when_no_limits_are_passed(self, sp, monkeypatch):
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_FULL_ROWS", "1000")
        out = sp.resolve_stats_policy("xorq", "parquet", 5_000, 10, host_tier="full")
        assert out["tier_target"] == "scalar"
        assert out["reason"] == "ceiling"

    def test_the_full_auto_cell_bound_comes_from_the_environment(self, sp, monkeypatch):
        args = ("xorq", "parquet", 5_000, 10)
        assert sp.resolve_stats_policy(*args)["tier_target"] == "full"
        monkeypatch.setenv("BUCKAROO_STATS_FULL_AUTO_CELLS", "1000")
        out = sp.resolve_stats_policy(*args)
        assert out["tier_target"] == "scalar"
        assert out["reason"] == "size"

    def test_the_full_ceiling_cell_bound_comes_from_the_environment(self, sp, monkeypatch):
        args = ("xorq", "parquet", 5_000, 10)
        assert sp.resolve_stats_policy(*args, host_tier="full")["tier_target"] == "full"
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_FULL_CELLS", "1000")
        out = sp.resolve_stats_policy(*args, host_tier="full")
        assert out["tier_target"] == "scalar"
        assert out["reason"] == "ceiling"

    def test_the_scalar_ceiling_comes_from_the_environment(self, sp, monkeypatch):
        args = ("xorq", "parquet", 5_000, 10)
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_SCALAR_CELLS", "1000")
        out = sp.resolve_stats_policy(*args, host_tier="scalar")
        assert out["tier_target"] == "schema"
        assert out["reason"] == "ceiling"

    def test_the_environment_is_read_on_each_call(self, sp, monkeypatch):
        args = ("xorq", "parquet", 5_000, 10)
        assert sp.resolve_stats_policy(*args, host_tier="full")["tier_target"] == "full"
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_FULL_ROWS", "1000")
        assert sp.resolve_stats_policy(*args, host_tier="full")["tier_target"] == "scalar"


class _CountingFile(io.BytesIO):
    """A binary file that counts the bytes read out of it."""

    def __init__(self, data):
        super().__init__(data)
        self.bytes_read = 0

    def read(self, size=-1):
        out = super().read(size)
        self.bytes_read += len(out)
        return out

    def read1(self, size=-1):
        out = super().read1(size)
        self.bytes_read += len(out)
        return out

    def readinto(self, b):
        n = super().readinto(b)
        self.bytes_read += n
        return n


def _parquet_bytes(rows, row_group_size):
    """Incompressible float columns, so the file is mostly row-group data."""
    rng = np.random.default_rng(0)
    table = pa.table({f"c{i}": rng.random(rows) for i in range(4)})
    buf = io.BytesIO()
    pq.write_table(table, buf, row_group_size=row_group_size, compression="none")
    return buf.getvalue()


class TestProbes:
    def test_parquet_rows_reads_the_footer_and_no_row_group(self, sp):
        data = _parquet_bytes(200_000, 50_000)
        source = _CountingFile(data)
        assert sp.probe_parquet_rows(source) == 200_000
        assert len(data) > 5_000_000
        assert source.bytes_read * 20 < len(data)

    def test_parquet_rows_from_a_path_decodes_no_data(self, sp, tmp_path, monkeypatch):
        path = tmp_path / "t.parquet"
        path.write_bytes(_parquet_bytes(120_000, 40_000))

        def boom(*args, **kwargs):
            raise AssertionError("the footer probe decoded row-group data")

        monkeypatch.setattr(pq.ParquetFile, "read", boom)
        monkeypatch.setattr(pq.ParquetFile, "read_row_group", boom)
        monkeypatch.setattr(pq.ParquetFile, "iter_batches", boom)
        monkeypatch.setattr(pq, "read_table", boom)
        assert sp.probe_parquet_rows(str(path)) == 120_000
        assert sp.probe_parquet_rows(path) == 120_000

    def test_parquet_rows_of_an_empty_file(self, sp):
        buf = io.BytesIO()
        pq.write_table(pa.table({"a": pa.array([], type=pa.int64())}), buf)
        assert sp.probe_parquet_rows(io.BytesIO(buf.getvalue())) == 0

    def test_dtypes_of_a_pandas_frame(self, sp):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        assert sp.probe_dtypes(df) == {"a": "int64", "b": str(df["b"].dtype)}

    def test_dtypes_of_a_polars_frame(self, sp):
        df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        assert sp.probe_dtypes(df) == {"a": "Int64", "b": "String"}

    @pytest.mark.filterwarnings("error")
    def test_dtypes_of_a_polars_scan_run_no_collect(self, sp, tmp_path, monkeypatch):
        """Reading ``LazyFrame.dtypes`` resolves the plan and warns, so the
        error filter also pins that the probe goes through ``collect_schema``."""
        path = tmp_path / "t.parquet"
        pl.DataFrame({"a": [1, 2], "b": ["x", "y"]}).write_parquet(path)
        lf = pl.scan_parquet(path)

        def boom(*args, **kwargs):
            raise AssertionError("the dtype probe collected a LazyFrame")

        monkeypatch.setattr(pl.LazyFrame, "collect", boom)
        assert sp.probe_dtypes(lf) == {"a": "Int64", "b": "String"}

    def test_dtypes_keep_column_order(self, sp):
        df = pd.DataFrame({"z": [1], "a": [2], "m": [3]})
        assert list(sp.probe_dtypes(df)) == ["z", "a", "m"]

    def test_dtypes_of_something_without_a_schema_raise(self, sp):
        with pytest.raises(TypeError):
            sp.probe_dtypes(object())

    def test_xorq_probes_and_a_known_count_execute_nothing(self, sp, monkeypatch):
        """The count is an input: the caller passes the one load already took
        (``_expr_count``) and the policy never runs one itself."""
        xo = pytest.importorskip("xorq.api")
        from xorq.vendor.ibis.expr.types.core import Expr

        expr = xo.memtable({"a": [1, 2, 3], "b": ["x", "y", "z"]}, name="t")

        def boom(*args, **kwargs):
            raise AssertionError("a probe or the policy executed a xorq query")

        for name in ("execute", "to_pyarrow", "to_pyarrow_batches", "to_pandas"):
            if hasattr(Expr, name):
                monkeypatch.setattr(Expr, name, boom)

        dtypes = sp.probe_dtypes(expr)
        assert dtypes == {"a": "int64", "b": "string"}
        out = sp.resolve_stats_policy("xorq", "expr", 78_000_000, len(dtypes), host_tier="full")
        assert out["reason"] == "ceiling"


class TestRoutePolarsEntry:
    def test_above_r_goes_to_xorq(self, sp, lim):
        r = lim.polars_route_rows
        assert sp.route_polars_entry(r + 1, 43, limits=lim) == "xorq"
        assert sp.route_polars_entry(78_000_000, 44, limits=lim) == "xorq"

    def test_at_and_below_r_stay_eager(self, sp, lim):
        r = lim.polars_route_rows
        assert sp.route_polars_entry(r, 43, limits=lim) == "eager"
        assert sp.route_polars_entry(52_814, 27, limits=lim) == "eager"
        assert sp.route_polars_entry(0, 0, limits=lim) == "eager"

    def test_r_comes_from_the_limits_object(self, sp):
        lim = sp.StatsLimits(polars_route_rows=1_000)
        assert sp.route_polars_entry(1_001, 3, limits=lim) == "xorq"
        assert sp.route_polars_entry(1_000, 3, limits=lim) == "eager"

    def test_r_comes_from_the_environment_by_default(self, sp, monkeypatch):
        assert sp.route_polars_entry(5_000, 3) == "eager"
        monkeypatch.setenv("BUCKAROO_POLARS_ROUTE_ROWS", "1000")
        assert sp.route_polars_entry(5_000, 3) == "xorq"

    @pytest.mark.parametrize("rows, expected",
        [(0, "eager"), (7_999_999, "eager"), (8_000_000, "eager"), (8_000_001, "xorq"), (10_000_000, "xorq"),
         (10_800_000, "xorq")])
    def test_default_r_is_8m_rows(self, sp, rows, expected):
        """Equal, one below and one above R, on the module defaults; 10.8M
        rows (parking_2017) was eager under the old 10M threshold."""
        assert sp.route_polars_entry(rows, 43) == expected

    def test_defaults_route_the_78m_row_entry_to_xorq(self, sp):
        assert sp.route_polars_entry(78_000_000, 44) == "xorq"

    def test_the_result_is_one_of_two_strings(self, sp, lim):
        for rows in (0, 10_000_000, 10_000_001):
            assert sp.route_polars_entry(rows, 43, limits=lim) in ("xorq", "eager")

    @pytest.mark.parametrize("rows, cols", [(-1, 3), (3, -1), (None, 3), (1.5, 3)])
    def test_bad_counts_are_rejected(self, sp, lim, rows, cols):
        with pytest.raises((TypeError, ValueError)):
            sp.route_polars_entry(rows, cols, limits=lim)


# ---------------------------------------------------------------------------
# The policy on the session and the wire (rows-first p33)
# ---------------------------------------------------------------------------

# The table the wire tests load: five rows and three columns.
ESTIMATE = {"rows": 5, "cols": 3}
ONDEMAND_CAPS = frozenset({"stats_update", "stats_ondemand"})
UPDATE_CAPS = frozenset({"stats_update"})
LEGACY_CAPS = frozenset()

# Limits that put a five-by-three table in each tier.
SCALAR_BY_SIZE = dict(full_auto_rows=3, scalar_auto_cells=1_000)
SCHEMA_BY_SIZE = dict(full_auto_rows=3, scalar_auto_cells=10)
FULL_OVER_CEILING = dict(ceiling_full_rows=3)
SCALAR_OVER_CEILING = dict(ceiling_scalar_cells=10)


def _session(sp, stats_tier="auto", delivery="deferred", limits=None, resolve=True):
    """A buckaroo-mode session after a load that resolved its policy and began
    its first stats generation, the way ``/load_expr`` leaves one."""
    session = session_mod.SessionState(session_id="s", path="p")
    session.mode = "buckaroo"
    session.df_meta = {"total_rows": 5}
    session.stats_tier, session.stats_delivery = stats_tier, delivery
    session.stats_policy = (
        sp.resolve_stats_policy("xorq", "xorq_build", 5, 3, host_tier=stats_tier,
            limits=sp.StatsLimits(**(limits or {})))
        if resolve else None)
    session_mod.begin_stats_generation(session)
    return session


def _client(caps):
    return SimpleNamespace(caps=caps, search_string="")


# (host tier, delivery, limits) -> what an ``stats_ondemand`` client is told.
# A field equal to its documented default is left out, and ``tier_target`` and
# ``estimate`` are always there once a policy is reported.
POLICY_FRAMES = [
    ("auto", "deferred", {}, {"status": "pending", "tier": "schema", "gen": 1, "tier_target": "full",
        "requestable": [], "estimate": ESTIMATE}),
    ("auto", "deferred", SCALAR_BY_SIZE, {"status": "not_computed", "tier": "schema", "gen": 1, "reason": "size",
        "tier_target": "scalar", "estimate": ESTIMATE}),
    ("auto", "deferred", SCHEMA_BY_SIZE, {"status": "not_computed", "tier": "schema", "gen": 1, "reason": "size",
        "tier_target": "schema", "auto_request": False, "requestable": ["scalar", "full"], "estimate": ESTIMATE}),
    ("full", "deferred", FULL_OVER_CEILING, {"status": "not_computed", "tier": "schema", "gen": 1,
        "reason": "ceiling", "tier_target": "scalar", "requestable": [], "estimate": ESTIMATE}),
    ("scalar", "deferred", {}, {"status": "not_computed", "tier": "schema", "gen": 1, "reason": "host",
        "tier_target": "scalar", "estimate": ESTIMATE}),
    ("schema", "deferred", {}, {"status": "not_computed", "tier": "schema", "gen": 1, "reason": "host",
        "tier_target": "schema", "auto_request": False, "requestable": ["scalar", "full"], "estimate": ESTIMATE}),
    ("scalar", "inline", SCALAR_OVER_CEILING, {"status": "not_computed", "tier": "schema", "gen": 1,
        "reason": "ceiling", "tier_target": "schema", "auto_request": False, "requestable": [], "estimate": ESTIMATE}),
    ("schema", "inline", {}, {"status": "not_computed", "tier": "schema", "gen": 1, "reason": "host",
        "tier_target": "schema", "auto_request": False, "requestable": ["scalar", "full"], "estimate": ESTIMATE}),
]


class TestStatsFieldDefaults:
    """What a client assumes for a ``df_meta.stats`` field the server leaves out."""

    def test_a_frame_with_no_stats_is_complete(self):
        """An old server sends no ``df_meta.stats``, and a new client reads it as complete."""
        assert session_mod.stats_with_defaults({"total_rows": 3}) == {"status": "complete", "tier": "full",
            "tier_target": "full", "gen": None, "reason": None, "auto_request": True, "requestable": ["full"],
            "estimate": None, "omitted_keys": [], "approx_keys": [], "demand_columns": []}

    def test_a_pending_frame_is_headed_for_full(self):
        out = session_mod.stats_with_defaults({"stats": {"status": "pending", "tier": "schema", "gen": 3}})
        assert (out["status"], out["tier"], out["tier_target"], out["gen"]) == ("pending", "schema", "full", 3)
        assert (out["auto_request"], out["requestable"]) == (True, ["full"])

    def test_a_not_computed_frame_without_a_target_targets_the_tier_it_has(self):
        out = session_mod.stats_with_defaults({"stats": {"status": "not_computed", "tier": "schema", "gen": 2,
            "reason": "host"}})
        assert (out["tier_target"], out["reason"]) == ("schema", "host")

    def test_fields_the_frame_carries_win(self):
        stats = {"status": "not_computed", "tier": "schema", "gen": 2, "reason": "size", "tier_target": "scalar",
            "auto_request": False, "requestable": ["scalar", "full"], "estimate": ESTIMATE, "omitted_keys": ["a"],
            "approx_keys": ["b"], "demand_columns": ["c"]}
        out = session_mod.stats_with_defaults({"stats": stats})
        assert {key: out[key] for key in stats} == stats

    def test_the_defaults_are_not_shared_between_calls(self):
        first = session_mod.stats_with_defaults({})
        first["requestable"].append("scalar")
        first["omitted_keys"].append("x")
        second = session_mod.stats_with_defaults({})
        assert (second["requestable"], second["omitted_keys"]) == (["full"], [])

    def test_the_documented_defaults(self):
        assert session_mod.STATS_FIELD_DEFAULTS == {"auto_request": True, "requestable": ["full"], "omitted_keys": [],
            "approx_keys": [], "demand_columns": []}
        assert session_mod.STATS_TIER_REQUESTS == ("auto", "full", "scalar", "schema")
        assert session_mod.STATS_REASONS == ("size", "host", "cost", "ceiling")


class TestInitialStatsStatus:
    @pytest.mark.parametrize("stats_tier, delivery, policy, expected", [
        ("full", "inline", None, ("complete", None)),
        ("full", "deferred", None, ("pending", None)),
        ("schema", "inline", None, ("not_computed", "host")),
        ("scalar", "deferred", None, ("not_computed", "host")),
        # auto resolves against a schema-tier dataflow, which an inline session never has.
        ("auto", "inline", None, ("complete", None)),
        ("auto", "deferred", None, ("pending", None)),
        ("auto", "deferred", {"tier_target": "full", "reason": None}, ("pending", None)),
        ("auto", "deferred", {"tier_target": "scalar", "reason": "size"}, ("not_computed", "size")),
        ("auto", "deferred", {"tier_target": "schema", "reason": "size"}, ("not_computed", "size")),
        ("full", "deferred", {"tier_target": "scalar", "reason": "ceiling"}, ("not_computed", "ceiling")),
        ("schema", "deferred", {"tier_target": "schema", "reason": "host"}, ("not_computed", "host")),
        ("scalar", "inline", {"tier_target": "schema", "reason": "ceiling"}, ("not_computed", "ceiling"))])
    def test_the_status_follows_the_pair_and_the_policy(self, stats_tier, delivery, policy, expected):
        assert session_mod.initial_stats_status(stats_tier, delivery, policy) == expected

    @pytest.mark.parametrize("stats_tier, delivery, expected", [
        ("full", "inline", "full"), ("auto", "inline", "full"), ("full", "deferred", "schema"),
        ("auto", "deferred", "schema"), ("scalar", "inline", "schema"), ("schema", "inline", "schema"),
        ("scalar", "deferred", "schema")])
    def test_the_dataflow_is_built_at_the_schema_tier_unless_stats_run_inline(self, stats_tier, delivery, expected):
        """No scalar-tier units exist yet, so a scalar target builds at the schema tier."""
        assert session_mod.dataflow_stats_tier(stats_tier, delivery) == expected


class TestStatsMeta:
    @pytest.mark.parametrize("stats_tier, delivery, limits, expected", POLICY_FRAMES)
    def test_a_stats_ondemand_client_is_told_the_policy(self, sp, stats_tier, delivery, limits, expected):
        session = _session(sp, stats_tier, delivery, limits)
        assert session_mod.stats_meta(session) == expected
        message = session_mod.build_state_message(session)
        assert message["df_meta"] == {"total_rows": 5, "stats": expected}

    @pytest.mark.parametrize("stats_tier, limits", [("auto", SCALAR_BY_SIZE), ("auto", SCHEMA_BY_SIZE),
        ("full", FULL_OVER_CEILING)])
    def test_a_client_without_stats_ondemand_is_told_the_stats_are_on_their_way(self, sp, stats_tier, limits):
        """A target the server chose below full is applied only for a client that
        can take it; the others are served as a deferred session headed for full."""
        session = _session(sp, stats_tier, "deferred", limits)
        pending = {"status": "pending", "tier": "schema", "gen": 1}
        assert session_mod.stats_meta(session, ondemand=False) == pending
        assert session_mod.build_state_message(session, ondemand=False)["df_meta"]["stats"] == pending

    @pytest.mark.parametrize("stats_tier, delivery, limits, reason", [
        ("scalar", "deferred", {}, "host"), ("schema", "deferred", {}, "host"), ("schema", "inline", {}, "host"),
        ("scalar", "inline", SCALAR_OVER_CEILING, "ceiling")])
    def test_a_tier_the_host_named_reaches_every_client(self, sp, stats_tier, delivery, limits, reason):
        """The host chose it, so there is nothing for an older client to complete,
        and it gets the status without the policy fields."""
        session = _session(sp, stats_tier, delivery, limits)
        assert session_mod.stats_meta(session, ondemand=False) == {"status": "not_computed", "tier": "schema",
            "gen": 1, "reason": reason}

    @pytest.mark.parametrize("ondemand", [True, False])
    def test_an_explicit_full_within_the_ceiling_reports_no_policy(self, sp, ondemand):
        """The message is the one sent before the policy existed, though the
        policy is resolved and recorded."""
        session = _session(sp, "full", "deferred")
        assert session.stats_policy["tier_target"] == "full"
        assert session_mod.stats_meta(session, ondemand=ondemand) == {"status": "pending", "tier": "schema", "gen": 1}
        inline = _session(sp, "full", "inline", resolve=False)
        assert session_mod.stats_meta(inline, ondemand=ondemand) is None
        assert session_mod.build_state_message(inline, ondemand=ondemand)["df_meta"] == {"total_rows": 5}

    @pytest.mark.parametrize("stats_tier, limits",
        [("auto", {}), ("auto", SCALAR_BY_SIZE), ("full", FULL_OVER_CEILING)])
    def test_a_completed_session_reports_no_policy(self, sp, stats_tier, limits):
        session = _session(sp, stats_tier, "deferred", limits)
        session.stats_status, session.stats_reason = "complete", None
        assert session_mod.stats_meta(session) == {"status": "complete", "tier": "full", "gen": 1}

    def test_the_gen_follows_the_generation_and_the_status_restarts_from_the_policy(self, sp):
        session = _session(sp, "auto", "deferred", SCALAR_BY_SIZE)
        session.stats_status, session.stats_reason = "complete", None
        session_mod.begin_stats_generation(session)
        assert session_mod.stats_meta(session) == {"status": "not_computed", "tier": "schema", "gen": 2,
            "reason": "size", "tier_target": "scalar", "estimate": ESTIMATE}

    def test_omitted_approx_and_demand_keys_ride_along_when_there_are_some(self, sp):
        session = _session(sp, "auto", "deferred", SCALAR_BY_SIZE)
        assert not {"omitted_keys", "approx_keys", "demand_columns"} & set(session_mod.stats_meta(session))
        session.stats_policy.update(omitted_keys=["value_counts"], approx_keys=["distinct_count"],
            demand_columns=["a", "b"])
        stats = session_mod.stats_meta(session)
        assert (stats["omitted_keys"], stats["approx_keys"], stats["demand_columns"]) == (
            ["value_counts"], ["distinct_count"], ["a", "b"])
        # A client reads what is left out as empty.
        session.stats_policy.update(omitted_keys=[], approx_keys=[], demand_columns=[])
        assert not {"omitted_keys", "approx_keys", "demand_columns"} & set(session_mod.stats_meta(session))

    def test_every_reason_the_server_sends_is_a_documented_one(self):
        for *_, expected in POLICY_FRAMES:
            assert expected.get("reason", "size") in session_mod.STATS_REASONS


class TestPolicyForTheSession:
    """``resolve_session_policy``: what a load handler resolves, and when."""

    @pytest.mark.parametrize("stats_tier", ["auto", "full", "scalar", "schema"])
    def test_a_schema_dataflow_resolves_against_the_count_it_has(self, stats_tier):
        out = stats_wire.resolve_session_policy(stats_tier, "schema", 5, 3)
        assert out["estimate"] == ESTIMATE
        assert out["tier_target"] == {"auto": "full", "full": "full", "scalar": "scalar", "schema": "schema"}[stats_tier]

    def test_a_dataflow_that_ran_its_stats_has_nothing_to_resolve(self):
        assert stats_wire.resolve_session_policy("full", "full", 5, 3) is None
        assert stats_wire.resolve_session_policy("auto", "full", 5_000_000_000, 40) is None

    def test_the_ceiling_clips_a_host_that_asks_for_full(self, sp):
        out = stats_wire.resolve_session_policy("full", "schema", 78_000_000, 44)
        assert (out["tier_target"], out["reason"]) == ("scalar", "ceiling")

    def test_the_limits_are_read_on_each_call(self, monkeypatch):
        assert stats_wire.resolve_session_policy("auto", "schema", 5, 3)["tier_target"] == "full"
        monkeypatch.setenv("BUCKAROO_STATS_FULL_AUTO_ROWS", "3")
        assert stats_wire.resolve_session_policy("auto", "schema", 5, 3)["tier_target"] == "scalar"


class TestCapabilities:
    def test_the_second_bit_is_named(self):
        assert stats_wire.STATS_UPDATE_CAP == "stats_update"
        assert stats_wire.STATS_ONDEMAND_CAP == "stats_ondemand"
        assert stats_wire.parse_caps("stats_update,stats_ondemand") == ONDEMAND_CAPS

    @pytest.mark.parametrize("caps, expected", [
        (ONDEMAND_CAPS, True), (UPDATE_CAPS, False), (LEGACY_CAPS, False),
        # The bit means the client also merges stats_update; alone it is not enough.
        (frozenset({"stats_ondemand"}), False)])
    def test_only_stats_update_with_stats_ondemand_counts_as_ondemand(self, caps, expected):
        assert stats_wire.client_has_ondemand(_client(caps)) is expected

    def test_a_client_with_no_caps_attribute_is_not_ondemand(self):
        assert stats_wire.client_has_ondemand(SimpleNamespace()) is False

    @pytest.mark.parametrize("caps, expected", [(ONDEMAND_CAPS, False), (UPDATE_CAPS, True), (LEGACY_CAPS, True)])
    def test_a_policy_target_below_full_is_missing_stats_to_every_client_but_an_ondemand_one(self, sp, caps, expected):
        session = _session(sp, "auto", "deferred", SCHEMA_BY_SIZE)
        assert stats_wire.stats_to_pull(session, _client(caps)) is expected

    @pytest.mark.parametrize("caps", [ONDEMAND_CAPS, UPDATE_CAPS, LEGACY_CAPS])
    def test_a_pending_session_has_stats_to_pull_for_everyone(self, sp, caps):
        assert stats_wire.stats_to_pull(_session(sp, "auto", "deferred"), _client(caps)) is True

    @pytest.mark.parametrize("caps", [ONDEMAND_CAPS, UPDATE_CAPS, LEGACY_CAPS])
    def test_a_tier_the_host_named_has_nothing_to_pull(self, sp, caps):
        assert stats_wire.stats_to_pull(_session(sp, "schema", "deferred"), _client(caps)) is False
        assert stats_wire.stats_to_pull(_session(sp, "scalar", "deferred"), _client(caps)) is False


# ---------------------------------------------------------------------------
# Guards for huge sources (rows-first p37)
# ---------------------------------------------------------------------------

GUARD_ENV_FIELDS = {"BUCKAROO_SORT_DISABLE_ROWS": "sort_disable_rows",
    "BUCKAROO_SEARCH_DISABLE_ROWS": "search_disable_rows"}
# The provisional defaults, written out so a change to a module constant has to
# change a test too. Search has no default threshold: the server never refuses a
# search (plan 3 question 7), so the flag is only ever turned off by a host.
GUARD_DEFAULTS = {"sort_disable_rows": 25_000_000, "search_disable_rows": None}
ENABLED = {"sort": "enabled", "search": "enabled"}


@pytest.fixture(autouse=True)
def clean_guard_env(monkeypatch):
    """A developer's own sort and search thresholds must not leak in."""
    for name in GUARD_ENV_FIELDS:
        monkeypatch.delenv(name, raising=False)


def _guard_api(sp, name):
    api = getattr(sp, name, None)
    assert api is not None, f"buckaroo.server.stats_policy.{name} does not exist"
    return api


def _guards(sp, backend, rows, cols=10, source_kind="parquet", **limits):
    """``resolve_source_guards`` on the module defaults, or on the limits given."""
    resolve = _guard_api(sp, "resolve_source_guards")
    if limits:
        return resolve(backend, source_kind, rows, cols, limits=_guard_api(sp, "GuardLimits")(**limits))
    return resolve(backend, source_kind, rows, cols)


class TestGuardLimits:
    def test_the_defaults_are_the_provisional_values(self, sp):
        assert dataclasses.asdict(_guard_api(sp, "GuardLimits")()) == GUARD_DEFAULTS
        assert getattr(sp, "DEFAULT_SORT_DISABLE_ROWS", None) == GUARD_DEFAULTS["sort_disable_rows"]
        assert getattr(sp, "DEFAULT_SEARCH_DISABLE_ROWS", "missing") is None

    def test_from_env_with_a_clean_environment_is_the_default_set(self, sp):
        assert dataclasses.asdict(_guard_api(sp, "GuardLimits").from_env()) == GUARD_DEFAULTS

    @pytest.mark.parametrize("name, field", GUARD_ENV_FIELDS.items())
    def test_each_variable_overrides_its_field(self, sp, monkeypatch, name, field):
        monkeypatch.setenv(name, "12345")
        assert getattr(_guard_api(sp, "GuardLimits").from_env(), field) == 12345

    def test_underscored_integers_are_accepted(self, sp, monkeypatch):
        monkeypatch.setenv("BUCKAROO_SORT_DISABLE_ROWS", "2_000_000")
        assert _guard_api(sp, "GuardLimits").from_env().sort_disable_rows == 2_000_000

    @pytest.mark.parametrize("name, field", GUARD_ENV_FIELDS.items())
    @pytest.mark.parametrize("bad", ["lots", "-5", "1.5"])
    def test_invalid_value_falls_back_to_the_default_and_warns(self, sp, monkeypatch, caplog, name, field, bad):
        monkeypatch.setenv(name, bad)
        with caplog.at_level(logging.WARNING):
            limits = _guard_api(sp, "GuardLimits").from_env()
        assert getattr(limits, field) == GUARD_DEFAULTS[field]
        assert name in caplog.text

    def test_empty_value_means_unset(self, sp, monkeypatch):
        monkeypatch.setenv("BUCKAROO_SORT_DISABLE_ROWS", "")
        assert _guard_api(sp, "GuardLimits").from_env().sort_disable_rows == GUARD_DEFAULTS["sort_disable_rows"]


# (backend, rows, limits) -> (sort, search). 10.8M x 43 is parking_2017; the
# 42.3M, 54.1M and 78.0M entries are the three tallyman loads over 70 s.
SOURCE_GUARD_TABLE = [
    ("xorq", 0, {}, ("enabled", "enabled")),
    ("xorq", 52_814, {}, ("enabled", "enabled")),
    ("xorq", 10_800_000, {}, ("enabled", "enabled")),
    ("xorq", 24_999_999, {}, ("enabled", "enabled")),
    ("xorq", 25_000_000, {}, ("enabled", "enabled")),
    ("xorq", 25_000_001, {}, ("disabled", "enabled")),
    ("xorq", 42_300_000, {}, ("disabled", "enabled")),
    ("xorq", 54_100_000, {}, ("disabled", "enabled")),
    ("xorq", 78_000_000, {}, ("disabled", "enabled")),
    ("xorq", 10**12, {}, ("disabled", "enabled")),
    # Eager backends keep both: their windows come from a bounded frame.
    ("pandas", 78_000_000, {}, ("enabled", "enabled")),
    ("polars", 78_000_000, {}, ("enabled", "enabled")),
    ("polars", 78_000_000, {"sort_disable_rows": 1, "search_disable_rows": 1}, ("enabled", "enabled")),
    # The sort threshold: equal, one above, and none at all.
    ("xorq", 1000, {"sort_disable_rows": 1000}, ("enabled", "enabled")),
    ("xorq", 1001, {"sort_disable_rows": 1000}, ("disabled", "enabled")),
    ("xorq", 10**12, {"sort_disable_rows": None}, ("enabled", "enabled")),
    # The search threshold is its own number.
    ("xorq", 1000, {"search_disable_rows": 1000}, ("enabled", "enabled")),
    ("xorq", 1001, {"search_disable_rows": 1000}, ("enabled", "disabled")),
    ("xorq", 1001, {"sort_disable_rows": 5000, "search_disable_rows": 1000}, ("enabled", "disabled")),
    ("xorq", 5001, {"sort_disable_rows": 5000, "search_disable_rows": 1000}, ("disabled", "disabled")),
]


def _source_guard_id(case):
    backend, rows, limits, _expected = case
    return f"{backend}-{rows}-{'-'.join(f'{k}={v}' for k, v in limits.items()) or 'defaults'}"


class TestResolveSourceGuards:
    @pytest.mark.parametrize("backend, rows, limits, expected", SOURCE_GUARD_TABLE,
        ids=[_source_guard_id(case) for case in SOURCE_GUARD_TABLE])
    def test_the_table(self, sp, backend, rows, limits, expected):
        assert _guards(sp, backend, rows, **limits) == dict(zip(("sort", "search"), expected))

    def test_the_result_has_exactly_the_two_flags(self, sp):
        assert set(_guards(sp, "xorq", 5)) == {"sort", "search"}

    def test_the_column_count_does_not_move_a_row_threshold(self, sp):
        assert _guards(sp, "xorq", 25_000_000, cols=1) == _guards(sp, "xorq", 25_000_000, cols=500) == ENABLED

    def test_the_guards_ignore_the_stats_thresholds(self, sp, monkeypatch):
        """A ceiling that refuses full stats for the entry leaves its sort alone."""
        monkeypatch.setenv("BUCKAROO_STATS_FULL_AUTO_ROWS", "1")
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_FULL_ROWS", "1")
        monkeypatch.setenv("BUCKAROO_STATS_CEILING_SCALAR_CELLS", "1")
        assert _guards(sp, "xorq", 5_000) == ENABLED

    def test_the_environment_is_read_on_each_call(self, sp):
        resolve = _guard_api(sp, "resolve_source_guards")
        assert resolve("xorq", "parquet", 5_000, 10) == ENABLED
        with pytest.MonkeyPatch.context() as env:
            env.setenv("BUCKAROO_SORT_DISABLE_ROWS", "1000")
            assert resolve("xorq", "parquet", 5_000, 10)["sort"] == "disabled"
        assert resolve("xorq", "parquet", 5_000, 10) == ENABLED

    def test_the_environment_sets_the_search_flag(self, sp, monkeypatch):
        monkeypatch.setenv("BUCKAROO_SEARCH_DISABLE_ROWS", "1000")
        assert _guard_api(sp, "resolve_source_guards")("xorq", "parquet", 5_000, 10) == {"sort": "enabled",
            "search": "disabled"}

    @pytest.mark.parametrize("rows, cols, error", [(-1, 3, ValueError), (5, -1, ValueError), (1.5, 3, TypeError),
        ("5", 3, TypeError), (5, None, TypeError)])
    def test_a_bad_count_is_refused_as_the_stats_policy_refuses_it(self, sp, rows, cols, error):
        with pytest.raises(error):
            _guard_api(sp, "resolve_source_guards")("xorq", "parquet", rows, cols)

    def test_a_source_kind_that_is_not_a_string_is_refused(self, sp):
        with pytest.raises(TypeError):
            _guard_api(sp, "resolve_source_guards")("xorq", None, 5, 3)


def _guarded(sort="enabled", search="enabled"):
    """A buckaroo-mode session whose load resolved these guard flags."""
    session = session_mod.SessionState(session_id="s", path="p")
    session.mode = "buckaroo"
    session.df_meta = {"total_rows": 5}
    session.source_guards = {"sort": sort, "search": search}
    return session


class TestGuardFlagsInDfMeta:
    """``df_meta.sort`` and ``df_meta.search``: sent when a session has turned
    one off, left out when it is on, which is what a client assumes."""

    def test_a_session_with_no_guards_by_default(self):
        assert getattr(session_mod.SessionState(session_id="s", path="p"), "source_guards", "missing") is None

    def test_the_documented_defaults(self):
        assert getattr(session_mod, "SOURCE_GUARD_DEFAULTS", None) == ENABLED

    def test_a_disabled_sort_is_reported(self):
        assert session_mod.build_state_message(_guarded(sort="disabled"))["df_meta"] == {"total_rows": 5,
            "sort": "disabled"}

    def test_a_disabled_search_is_reported(self):
        assert session_mod.build_state_message(_guarded(search="disabled"))["df_meta"] == {"total_rows": 5,
            "search": "disabled"}

    def test_both_flags_are_reported_when_both_are_off(self):
        assert session_mod.build_state_message(_guarded("disabled", "disabled"))["df_meta"] == {"total_rows": 5,
            "sort": "disabled", "search": "disabled"}

    @pytest.mark.parametrize("ondemand", [True, False])
    def test_every_client_is_told(self, ondemand):
        """The server refuses the sort whoever asks, so no capability gates the flag."""
        message = session_mod.build_state_message(_guarded(sort="disabled"), ondemand=ondemand)
        assert message["df_meta"]["sort"] == "disabled"

    def test_the_flags_ride_with_the_stats_status(self, sp):
        session = _session(sp, "auto", "deferred", SCALAR_BY_SIZE)
        session.source_guards = {"sort": "disabled", "search": "enabled"}
        df_meta = session_mod.build_state_message(session)["df_meta"]
        assert df_meta == {"total_rows": 5, "sort": "disabled", "stats": session_mod.stats_meta(session)}

    def test_a_client_reads_what_is_left_out_as_enabled(self):
        read = getattr(session_mod, "guards_with_defaults", None)
        assert read is not None, "session.guards_with_defaults does not exist"
        assert read({"total_rows": 5}) == ENABLED
        assert read({}) == ENABLED
        assert read(None) == ENABLED
        assert read({"sort": "disabled"}) == {"sort": "disabled", "search": "enabled"}
        assert read({"search": "disabled", "sort": "enabled"}) == {"sort": "enabled", "search": "disabled"}


class TestSortRefusal:
    """``sort_refusal``: the ``infinite_resp`` a sorted window gets when the
    session's sort is off, and nothing for any other request."""

    WINDOW = {"start": 0, "end": 5, "sourceName": "default", "origEnd": 5}

    @staticmethod
    def _refusal(session, payload):
        refuse = getattr(session_mod, "sort_refusal", None)
        assert refuse is not None, "session.sort_refusal does not exist"
        return refuse(session, payload)

    def test_a_sorted_window_is_refused_with_a_code(self):
        payload = {**self.WINDOW, "sort": "a", "sort_direction": "asc"}
        refusal = self._refusal(_guarded(sort="disabled"), payload)
        assert refusal is not None
        assert (refusal["type"], refusal["key"], refusal["length"]) == ("infinite_resp", payload, 0)
        assert refusal["error_code"] == "sort_disabled"
        assert isinstance(refusal["error_info"], str) and refusal["error_info"]
        assert "payload" not in refusal, "no rows travel with a refusal"

    @pytest.mark.parametrize("payload", [{}, {"sort": None}, {"sort": ""}, {"sort_direction": "asc"}])
    def test_a_window_with_no_sort_is_served(self, payload):
        assert self._refusal(_guarded(sort="disabled"), {**self.WINDOW, **payload}) is None

    def test_a_session_with_the_sort_on_serves_a_sorted_window(self):
        assert self._refusal(_guarded(), {**self.WINDOW, "sort": "a"}) is None
        assert self._refusal(_guarded(search="disabled"), {**self.WINDOW, "sort": "a"}) is None

    def test_a_session_that_resolved_no_guards_serves_a_sorted_window(self):
        session = session_mod.SessionState(session_id="s", path="p")
        assert self._refusal(session, {**self.WINDOW, "sort": "a"}) is None

    @pytest.mark.parametrize("payload", [None, "sort", ["sort"], 5])
    def test_a_payload_that_is_not_a_dict_is_not_refused(self, payload):
        assert self._refusal(_guarded(sort="disabled"), payload) is None


class TestResolveSessionGuards:
    """``stats_wire.resolve_session_guards``: what a load handler resolves, and
    for which sessions."""

    @staticmethod
    def _resolve(*args):
        resolve = getattr(stats_wire, "resolve_session_guards", None)
        assert resolve is not None, "stats_wire.resolve_session_guards does not exist"
        return resolve(*args)

    def test_a_schema_dataflow_resolves_against_the_count_it_has(self, monkeypatch):
        monkeypatch.setenv("BUCKAROO_SORT_DISABLE_ROWS", "3")
        assert self._resolve("schema", 5, 3) == {"sort": "disabled", "search": "enabled"}
        assert self._resolve("schema", 3, 3) == ENABLED

    def test_a_dataflow_that_ran_its_stats_has_no_guards(self, monkeypatch):
        """Only a session a host opened with a stats policy is guarded. One built
        the way it always was, with its stats inline, stays as it was."""
        monkeypatch.setenv("BUCKAROO_SORT_DISABLE_ROWS", "3")
        assert self._resolve("full", 5, 3) is None
        assert self._resolve("full", 5_000_000_000, 40) is None

    def test_the_defaults_guard_a_session_of_the_size_the_stats_ceiling_refuses(self):
        assert self._resolve("schema", 78_000_000, 44)["sort"] == "disabled"
        assert self._resolve("schema", 10_800_000, 43) == ENABLED

    def test_the_thresholds_are_read_on_each_call(self, monkeypatch):
        assert self._resolve("schema", 5, 3) == ENABLED
        monkeypatch.setenv("BUCKAROO_SORT_DISABLE_ROWS", "3")
        assert self._resolve("schema", 5, 3)["sort"] == "disabled"


def _grid_display(main_columns, left=(), summary_columns=()):
    """A ``df_display_args`` as the dataflow builds it: ``main`` is the display
    the infinite grid serves from the server, ``summary`` is a client-side grid."""
    def display(data_key, columns, left_columns):
        return {"data_key": data_key, "summary_stats_key": "all_stats",
            "df_viewer_config": {"pinned_rows": [], "column_config": list(columns),
                "left_col_configs": list(left_columns), "extra_grid_config": {}, "component_config": {}}}
    return {"main": display("main", main_columns, left), "summary": display("empty", summary_columns, ())}


class TestDisableSorting:
    """``disable_sorting``: the final pass that turns sorting off for every column
    of a display served by ``infinite_request``, after the klasses and the
    overrides have had their say."""

    @staticmethod
    def _disable(sp, display):
        return _guard_api(sp, "disable_sorting")(display)

    @staticmethod
    def _columns(display, key="main"):
        config = display[key]["df_viewer_config"]
        return config["column_config"] + config["left_col_configs"]

    def test_every_column_of_the_infinite_display_stops_sorting(self, sp):
        display = _grid_display(
            [{"col_name": "a", "header_name": "price"},
             {"col_name": "b", "header_name": "qty", "ag_grid_specs": {"minWidth": 90}},
             {"col_name": "c", "header_name": "category", "ag_grid_specs": {"sortable": True}},
             {"col_path": ("x", "y"), "field": "d", "ag_grid_specs": {"sortable": True, "minWidth": 70}}],
            left=[{"col_name": "index", "header_name": "index"}])
        out = self._disable(sp, display)
        assert [c["ag_grid_specs"]["sortable"] for c in self._columns(out)] == [False] * 5

    def test_the_other_column_specs_are_kept(self, sp):
        out = self._disable(sp, _grid_display([{"col_name": "b", "ag_grid_specs": {"minWidth": 90, "sortable": True}}]))
        assert out["main"]["df_viewer_config"]["column_config"][0]["ag_grid_specs"] == {"minWidth": 90,
            "sortable": False}

    def test_a_display_the_client_sorts_itself_is_left_alone(self, sp):
        summary = [{"col_name": "a", "header_name": "price", "ag_grid_specs": {"sortable": True}}, {"col_name": "b"}]
        display = _grid_display([{"col_name": "a"}], summary_columns=summary)
        out = self._disable(sp, display)
        assert out["summary"] == display["summary"]

    def test_the_rest_of_the_display_is_unchanged(self, sp):
        display = _grid_display([{"col_name": "a", "displayer_args": {"displayer": "obj"}}])
        out = self._disable(sp, display)
        main, held = out["main"], display["main"]
        assert (main["data_key"], main["summary_stats_key"]) == (held["data_key"], held["summary_stats_key"])
        for key in ("pinned_rows", "extra_grid_config", "component_config"):
            assert main["df_viewer_config"][key] == held["df_viewer_config"][key]
        assert main["df_viewer_config"]["column_config"][0]["displayer_args"] == {"displayer": "obj"}

    def test_the_display_given_is_not_changed(self, sp):
        display = _grid_display([{"col_name": "a", "ag_grid_specs": {"sortable": True}}, {"col_name": "b"}],
            left=[{"col_name": "index"}])
        before = json.dumps(display, sort_keys=True)
        out = self._disable(sp, display)
        assert json.dumps(display, sort_keys=True) == before
        assert out is not display

    @pytest.mark.parametrize("display", [{}, {"main": None}, {"main": {}}, {"main": {"data_key": "main"}},
        {"main": {"data_key": "main", "df_viewer_config": None}},
        {"main": {"data_key": "main", "df_viewer_config": {"column_config": None}}},
        {"main": {"data_key": "main", "df_viewer_config": {"column_config": []}}}])
    def test_a_display_that_is_not_the_usual_shape_does_not_raise(self, sp, display):
        assert isinstance(self._disable(sp, display), dict)

    def test_a_display_with_no_left_columns_is_handled(self, sp):
        display = _grid_display([{"col_name": "a"}])
        del display["main"]["df_viewer_config"]["left_col_configs"]
        out = self._disable(sp, display)
        assert out["main"]["df_viewer_config"]["column_config"][0]["ag_grid_specs"]["sortable"] is False
