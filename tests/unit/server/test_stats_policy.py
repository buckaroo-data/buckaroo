"""Unit tests for ``buckaroo.server.stats_policy`` (rows-first p31, p31b).

Everything here is pure Python: the policy is a function of numbers, the
probes read a schema or a parquet footer, and nothing needs a server. The
module is not wired into any handler, session or dataflow in this phase.

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

import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

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
