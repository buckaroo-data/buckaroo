"""Tests for the per-cell summary-stat cache (ADR-001).

A cell is one ``(column, stat)`` value, keyed by ``(scope_id, col, stat_hash)``.
These tests assert structure (which queries run, which cells are computed,
which parts are written), not wall-clock time.
"""

import datetime as dt
import functools
import importlib.metadata
import importlib.util
import inspect
import math
import shutil
import zoneinfo
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

xo = pytest.importorskip("xorq.api")

import xorq.vendor.ibis.expr.types.core as ibis_core  # noqa: E402

import buckaroo.customizations.histogram as histogram_module  # noqa: E402
from buckaroo import ddd_library  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402
from buckaroo.pluggable_analysis_framework import stat_cache as sc  # noqa: E402
from buckaroo.pluggable_analysis_framework.stat_func import (  # noqa: E402
    ColumnValue, StatFunc, StatKey, XorqColumn, XorqExecute, XorqExpr, stat)
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    TOTAL_LENGTH_KEY, XorqStatPipeline)


def _table():
    n = 40
    return xo.memtable(pa.table({
        "ints": pa.array([(i * 7) % 13 for i in range(n)], pa.int32()),
        "floats": pa.array([i * 0.5 for i in range(n)]),
        "strs": pa.array([f"s{i % 8}" for i in range(n)])}), name="t")


def _wide_table(ncols=25):
    return xo.memtable(pa.table({
        f"c{i}": pa.array([(j * 7 + i) % 17 for j in range(30)], pa.int64()) for i in range(ncols)}),
        name="wide")


def _pipeline(cache, stats=XORQ_STATS_V2):
    return XorqStatPipeline(stats, unit_test=False, cache_storage=cache)


def _parts(cache, scope_id):
    return sorted(cache.scope_dir(scope_id).glob("part-*.parquet"))


def _same(a, b) -> bool:
    """Equal and of the same type, recursively. NaN equals NaN and zeros keep
    their sign; pandas and numpy temporals must also keep their unit and
    timezone."""
    if type(a) is not type(b):
        return False
    if a is pd.NaT:
        return b is pd.NaT
    if isinstance(a, float):
        return math.isnan(b) if math.isnan(a) else a == b and math.copysign(1, a) == math.copysign(1, b)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        return list(a) == list(b) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (pd.Timestamp, pd.Timedelta)):
        return a == b and a.unit == b.unit and str(getattr(a, "tz", None)) == str(getattr(b, "tz", None))
    if isinstance(a, (np.datetime64, np.timedelta64)):
        return a.dtype == b.dtype and (a == b or (np.isnat(a) and np.isnat(b)))
    if isinstance(a, Decimal):
        return a.as_tuple() == b.as_tuple()
    return bool(a == b)


def _ddd_frames():
    """Every frame the DDD builds, pandas and polars, by name."""
    for name, fn in inspect.getmembers(ddd_library, inspect.isfunction):
        if fn.__module__ == ddd_library.__name__ and not name.startswith("_"):
            df = fn()
            if isinstance(df, (pd.DataFrame, pl.DataFrame)):
                yield name, df


def _ddd_values():
    """``(id, values)`` per DDD column: every value a stat can see in it, each
    cell and the whole column as a list, as pandas hands them over and as
    polars does (pandas frames converted where polars can)."""
    def polars_values(name, df):
        for col in df.columns:
            # to_list, not ser[i]: polars hands a list or array cell over as a Series.
            values = df[col].to_list()
            yield f"polars-{name}-{col}", values + [values]

    for name, df in _ddd_frames():
        if isinstance(df, pl.DataFrame):
            yield from polars_values(name, df)
            continue
        for j in range(df.shape[1]):
            ser = df.iloc[:, j]
            yield f"pandas-{name}-{j}", [ser.iloc[i] for i in range(len(ser))] + [ser.tolist()]
        if not isinstance(df.columns, pd.MultiIndex) and all(isinstance(c, str) for c in df.columns):
            try:
                converted = pl.from_pandas(df.reset_index(drop=True))
            except Exception:
                continue
            yield from polars_values(f"{name}-from-pandas", converted)


# DDD cases that fail today, by test id, with the issue tracking each. The
# xfails are strict, so a fix that makes one pass removes it from here.
_DDD_KNOWN_FAILURES = {
    "pandas-df_with_far_future_fixed_offset_timestamps-0": "#1053: a us Timestamp past 2262 isn't cached",
    **{f"pandas-df_with_nullable_dtypes-{j}": "#1053: pd.NA isn't cached" for j in range(4)},
    "polars-pl_df_with_temporal_edges-new_york": "#1053: a fold=1 datetime isn't cached",
    "polars-pl_df_with_temporal_edges-far_kolkata": "#1053: a datetime before year 1 UTC isn't cached",
    "df_with_far_future_fixed_offset_timestamps": "#1053: a pytz.FixedOffset datetime isn't cached",
    "df_with_infinity": "#1057: the failing histogram is the run's last query, never cached",
    "pl_df_with_temporal_edges": "#1057: the failing time histogram is the run's last query, never cached"}


def _ddd_params(cases):
    """A ``pytest.param`` per ``(id, value)``, xfail when it's a known failure."""
    return [pytest.param(v, id=i, marks=[pytest.mark.xfail(strict=True, reason=_DDD_KNOWN_FAILURES[i])]
        if i in _DDD_KNOWN_FAILURES else []) for i, v in cases]


def _nested(depth):
    """``1`` inside ``depth`` lists."""
    v: Any = 1
    for _ in range(depth):
        v = [v]
    return v


def _ddd_xorq_table(name):
    """The DDD frame ``name`` as a xorq table, or None when xorq can't load it
    (non-string column names, types arrow can't convert)."""
    df = dict(_ddd_frames())[name]
    try:
        if isinstance(df, pl.DataFrame):
            return xo.memtable(df.to_arrow(), name="t")
        if isinstance(df.columns, pd.MultiIndex) or not all(isinstance(c, str) for c in df.columns):
            return None
        return xo.memtable(pa.Table.from_pandas(df, preserve_index=False), name="t")
    except Exception:
        return None


@pytest.fixture(autouse=True)
def _pyarrow_default_timezones(monkeypatch):
    """Run under pyarrow's default timezone handling. Importing pandera sets
    ``PYARROW_IGNORE_TIMEZONE=1`` (for pyspark), and collecting
    ``test_buckaroo_pandera.py`` imports it for the whole session."""
    monkeypatch.delenv("PYARROW_IGNORE_TIMEZONE", raising=False)


class ExecSpy:
    """Records every backend query. Patches xorq's ``Expr.execute``, which the
    stat pipeline and ``_expr_count``'s ``count()`` both go through."""

    def __enter__(self):
        self.queries = []
        self._orig = ibis_core.Expr.execute
        spy = self

        def execute(expr, *args, **kwargs):
            spy.queries.append(expr)
            return spy._orig(expr, *args, **kwargs)

        ibis_core.Expr.execute = execute
        return self

    def __exit__(self, *exc):
        ibis_core.Expr.execute = self._orig

    def batch_cells(self):
        """``(col, stat)`` pairs folded into batch aggregates, from the
        ``col|stat`` output names the pipeline gives them."""
        cells = set()
        for q in self.queries:
            schema = getattr(q, "schema", None)
            if schema is None:
                continue
            cells |= {tuple(n.split("|", 1)) for n in schema().names if "|" in n}
        return cells

    def batch_queries(self):
        return [q for q in self.queries
                if getattr(q, "schema", None) and any("|" in n for n in q.schema().names)]


def _spy_data_touching_calls(monkeypatch, stats):
    """Wrap every stat that builds or runs a query, recording each call."""
    calls = []
    for obj in stats:
        sf = getattr(obj, "_stat_func", None)
        if sf is None or not any(r.type in (XorqColumn, XorqExpr, XorqExecute) for r in sf.requires):
            continue

        def wrapped(*args, _f=sf.func, _name=sf.name, **kwargs):
            calls.append(_name)
            return _f(*args, **kwargs)

        monkeypatch.setattr(sf, "func", wrapped)
    return calls


def _import_file(path, source):
    """Write ``source`` to ``path`` and import it as a module."""
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(fn):
    """The source digest a ``StatFunc`` built from ``fn`` keys its cells by."""
    return StatFunc("plus", fn, [StatKey("col", XorqColumn)], [StatKey("plus", int)], False).source_digest


# ============================================================
# Stats used by the tests below
# ============================================================


@stat()
def non_null(col: XorqColumn) -> int:
    return col.count()


@stat(column_filter=lambda dt: dt.is_integer() or dt.is_string())
def digits_max(col: XorqColumn) -> int:
    """Builds on every column it accepts, but fails at execution on a string
    column whose values aren't digits."""
    return col.cast("string").cast("int64").max()


@stat()
def low(col: XorqColumn) -> int:
    return col.min()


@stat()
def high(col: XorqColumn) -> int:
    return col.max()


@stat()
def first_value(col: XorqColumn) -> ColumnValue:
    """A value drawn from the column, whatever its type."""
    return col.arbitrary()


@stat()
def low_rows(expr: XorqExpr, execute: XorqExecute, orig_col_name: str, low: int) -> int:
    """A per-column query stat that depends on ``low``."""
    return int(execute(expr.filter(expr[orig_col_name] == low).count()))


# Column -> the exception the ``queried_rows`` stats raise for it, standing in
# for their query failing.
_QUERY_FAILURES: dict = {}


@stat()
def queried_rows(expr: XorqExpr, execute: XorqExecute, orig_col_name: str) -> int:
    """A per-column query stat."""
    if orig_col_name in _QUERY_FAILURES:
        raise _QUERY_FAILURES[orig_col_name]
    return int(execute(expr.count()))


@stat(default=-1)
def queried_rows_or_default(expr: XorqExpr, execute: XorqExecute, orig_col_name: str) -> int:
    """``queried_rows`` with a ``default`` standing in for a failure."""
    if orig_col_name in _QUERY_FAILURES:
        raise _QUERY_FAILURES[orig_col_name]
    return int(execute(expr.count()))


def _caused_by(err, cause):
    err.__cause__ = cause
    return err


# Failures that come from where a query ran, not from the stat.
_ENVIRONMENTAL_FAILURES = {"too-many-open-files": lambda: OSError(24, "Too many open files"),
    "snapshot-file-gone": lambda: FileNotFoundError(2, "No such file or directory", "part-0.parquet"),
    "object-store": lambda: Exception("External error: Object Store error: Generic S3 error: request failed"),
    "engine-io": lambda: Exception("IO error: Too many open files (os error 24)"),
    "wrapped-os-error": lambda: _caused_by(ValueError("reading the column failed"), OSError(5, "I/O error"))}

# Two post-processing steps in one file.
TWO_STEPS_SOURCE = '''\
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis


class HighOnly(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "high_only"

    @classmethod
    def post_process_df(cls, expr):
        return [expr.filter(expr.ints > 5), {}]


class LowOnly(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "low_only"

    @classmethod
    def post_process_df(cls, expr):
        return [expr.filter(expr.ints < 5), {}]
'''


# ============================================================
# Storage: parts, layout, round trip
# ============================================================


class TestStorage:
    def test_round_trip_keeps_each_value_and_its_type(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        numeric_hist = [{"name": "0-1", "population": 50.0}, {"name": "1-2", "population": 50.0}]
        cat_hist = [{"name": "a", "cat_pop": 60.0}, {"name": "b", "cat_pop": 40.0}]
        values = {
            "a": {"min@1": 3, "max@1": 2**63 + 5, "mean@2": 1.5, "std@2": float("nan"),
                  "distinct_count@3": None, "flag@4": True, "mode@5": "x", "dec@6": Decimal("1.25"),
                  "histogram@7": numeric_hist, "bins@8": [0.0, 0.5, 1.0], "empty@9": []},
            "b": {"min@1": -4.5, "histogram@7": cat_hist},
            None: {"length@0": 52814}}
        cache.write("s", values)
        got = cache.read("s").values

        assert set(got) == set(values)
        for col, cells in values.items():
            assert set(got[col]) == set(cells), col
            for sid, v in cells.items():
                back = got[col][sid]
                if isinstance(v, float) and math.isnan(v):
                    assert isinstance(back, float) and math.isnan(back)
                    continue
                assert back == v, (col, sid)
                assert type(back) is type(v), (col, sid)
        # Computed-as-None is a stored cell; never computed is absent.
        assert "distinct_count@3" in got["a"] and got["a"]["distinct_count@3"] is None
        assert "distinct_count@3" not in got["b"]

    def test_parts_live_in_the_scope_directory(self, tmp_path):
        cache = sc.StatCache.for_cache_storage_path(tmp_path)
        cache.write("scope1", {"a": {"min@1": 1}})
        parts = list((tmp_path / "parquet" / "v1" / "scope1").glob("part-*.parquet"))
        assert len(parts) == 1

    def test_newest_part_wins(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"x@1": 1}})
        cache.write("s", {"a": {"x@1": 2, "y@1": 3}, "b": {"x@1": 4}})
        scope = cache.read("s")
        assert scope.values == {"a": {"x@1": 2, "y@1": 3}, "b": {"x@1": 4}}
        assert scope.parts_read == 2

    def test_errors_round_trip_apart_from_values(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"ok@1": 5}}, errors={"a": {"bad@2": "Cannot cast string 'x'"}})
        scope = cache.read("s")
        assert scope.values == {"a": {"ok@1": 5}}
        assert scope.errors == {"a": {"bad@2": "Cannot cast string 'x'"}}

    def test_compaction_merges_parts_and_drops_dead_hashes(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        for i in range(sc.MAX_PARTS):
            cache.write("s", {"a": {f"stat{i}@1": i}})
        assert len(_parts(cache, "s")) == sc.MAX_PARTS
        cache.write("s", {"a": {"stat0@1": 100, "live@2": 1}},
            keep=lambda sid: sid != "stat1@1")
        assert len(_parts(cache, "s")) == 1
        values = cache.read("s").values["a"]
        assert values["stat0@1"] == 100
        assert values["live@2"] == 1
        assert "stat1@1" not in values
        assert values["stat7@1"] == 7

    def test_unreadable_part_is_skipped(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"x@1": 1}})
        (cache.scope_dir("s") / "part-0000-corrupt.parquet").write_bytes(b"not parquet")
        assert cache.read("s").values == {"a": {"x@1": 1}}

    def test_a_part_with_a_foreign_schema_is_skipped_and_compaction_still_runs(self, tmp_path):
        """A part that reads as parquet but isn't a stat cache part (no column
        or computed field) is skipped like an unreadable one, by reads and by
        compaction."""
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"x@1": 1}})
        pq.write_table(pa.table({"other": [1]}), cache.scope_dir("s") / "part-0000-foreign.parquet")
        assert cache.read("s").values == {"a": {"x@1": 1}}
        for i in range(sc.MAX_PARTS):
            cache.write("s", {"a": {f"stat{i}@1": i}})
        assert len(_parts(cache, "s")) <= sc.MAX_PARTS
        assert cache.read("s").values == {"a": {"x@1": 1, **{f"stat{i}@1": i for i in range(sc.MAX_PARTS)}}}

    @pytest.mark.parametrize("values", _ddd_params(_ddd_values()))
    def test_ddd_values_round_trip(self, tmp_path, values):
        """Every value a stat can see in a DDD column, each cell and the whole
        column as a list, as pandas and as polars hand them over, comes back
        with its own type and value."""
        cache = sc.StatCache(tmp_path)
        cells = {f"r{i}": {"v@x": v} for i, v in enumerate(values)}
        cache.write("s", cells)
        got = cache.read("s").values
        for col, cell in cells.items():
            assert col in got and "v@x" in got[col], f"{cell['v@x']!r} wasn't cached"
            assert _same(got[col]["v@x"], cell["v@x"]), f"{cell['v@x']!r} came back as {got[col]['v@x']!r}"

    @pytest.mark.parametrize("value",
        [pytest.param(pd.Timestamp("2020-01-01 00:00:05.000000001"), id="timestamp-ns"),
         pytest.param(pd.Timestamp("2020-01-01 05:00", tz="US/Eastern"), id="timestamp-tz"),
         pytest.param(pd.Timestamp("2020-01-05 00:00:01").as_unit("s"), id="timestamp-s"),
         pytest.param(pd.Timedelta("4 days").as_unit("s"), id="timedelta-s"),
         pytest.param(pd.Timedelta("1500ms").as_unit("ms"), id="timedelta-ms"),
         pytest.param(pd.Timedelta(5), id="timedelta-ns"),
         pytest.param(np.datetime64("2020-01-01T00:00:05.000000001", "ns"), id="datetime64-ns"),
         pytest.param({"p#lo": 1, "p#hi": 3}, id="struct-hash-key"),
         pytest.param({"a,b": 1, "a": 2}, id="struct-comma-key"),
         pytest.param({"big": 2**63 + 5, "small": 1}, id="struct-uint64"),
         pytest.param(Decimal("-0.00"), id="decimal-negative-zero"),
         pytest.param(-0.0, id="float-negative-zero"),
         pytest.param([1.0, float("nan"), None], id="list-nan-and-none"),
         pytest.param([-1, 2**63], id="list-int-and-uint64"),
         pytest.param([1, True], id="list-int-and-bool"),
         pytest.param([[1], ["a"], [1, "a"]], id="list-of-mixed-lists"),
         pytest.param([{"a": 1}, {"b": 2}], id="list-of-structs-with-different-fields"),
         pytest.param({"a": None, "b": None}, id="struct-all-null"),
         pytest.param(_nested(50), id="list-50-deep"),
         pytest.param([pd.NaT, pd.Timestamp("2020-01-01")], id="list-with-nat"),
         pytest.param(np.datetime64("2020", "Y"), id="datetime64-years"),
         pytest.param(np.timedelta64(3, "M"), id="timedelta64-months"),
         pytest.param(pd.Period("2020-01-01", freq="W-SUN"), id="period-weekly"),
         pytest.param(pd.Interval(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")), id="interval-of-timestamps"),
         pytest.param(pd.Timestamp("2020-01-01").tz_localize(dt.timezone(dt.timedelta(hours=5, minutes=30))),
             id="timestamp-fixed-offset"),
         pytest.param(dt.datetime.max, id="datetime-max"),
         pytest.param(dt.date.min, id="date-min"),
         pytest.param(dt.timedelta(days=-1, microseconds=1), id="timedelta-negative"),
         pytest.param([1, pd.NA], id="list-with-pd-na",
             marks=pytest.mark.xfail(strict=True, reason="#1053: pd.NA isn't cached")),
         pytest.param(pd.Timestamp("3000-01-01").as_unit("us"), id="timestamp-us-past-2262",
             marks=pytest.mark.xfail(strict=True, reason="#1053: stored as nanoseconds, which overflow")),
         pytest.param(pd.Timedelta(np.timedelta64(200_000 * 86_400, "s")), id="timedelta-s-past-ns-range",
             marks=pytest.mark.xfail(strict=True, reason="#1053: stored as nanoseconds, which overflow")),
         pytest.param(dt.datetime(2020, 11, 1, 1, 30, fold=1, tzinfo=zoneinfo.ZoneInfo("America/New_York")),
             id="datetime-fold-1", marks=pytest.mark.xfail(strict=True, reason="#1053: fold=1 never compares equal")),
         pytest.param({}, id="empty-struct",
             marks=pytest.mark.xfail(strict=True, reason="#1053: parquet can't write an empty struct")),
         pytest.param(np.datetime64(5, "10s"), id="datetime64-10s",
             marks=pytest.mark.xfail(strict=True, reason="#1053: the spec drops the unit's multiplier"))])
    def test_value_round_trips(self, tmp_path, value):
        """Values outside the DDD that stats return: pandas and numpy temporals
        keep their unit, timezone and nanoseconds, and struct keys may hold any
        character."""
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"v@x": value}})
        got = cache.read("s").values.get("a", {})
        assert "v@x" in got, f"{value!r} wasn't cached"
        assert _same(got["v@x"], value), f"{value!r} came back as {got['v@x']!r}"

    @pytest.mark.parametrize("value",
        [pytest.param(2**64, id="int-past-uint64"),
         pytest.param(np.complex128(1j), id="complex"),
         pytest.param({1, 2}, id="set"),
         pytest.param(np.array([1, 2]), id="ndarray"),
         pytest.param("\ud800", id="lone-surrogate"),
         pytest.param(dt.timedelta.max, id="timedelta-past-int64-microseconds"),
         # Each of these raises while the part is read back (#1052).
         pytest.param(pd.Timestamp("2020-01-01").tz_localize(dt.timezone(dt.timedelta(hours=5), "PKT")),
             id="timestamp-named-offset"),
         pytest.param(dt.datetime(2020, 1, 1, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))),
             id="datetime-fixed-offset"),
         pytest.param(dt.datetime(1, 1, 1, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata")), id="datetime-before-year-1-utc"),
         pytest.param(np.datetime64("NaT"), id="datetime64-generic-nat"),
         pytest.param(_nested(200), id="list-200-deep")])
    def test_a_value_that_does_not_round_trip_costs_only_its_own_cell(self, tmp_path, value):
        """A value the codec can't store, or can't read back exactly, is left
        out, and the rest of the part is cached."""
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"ok@1": 7, "v@x": value}})
        got = cache.read("s").values.get("a", {})
        assert got.get("ok@1") == 7, f"writing {value!r} lost the rest of the part"
        assert "v@x" not in got or _same(got["v@x"], value), f"{value!r} came back as {got['v@x']!r}"

    def test_an_aware_datetime_shifted_by_pyarrow_is_not_cached(self, tmp_path, monkeypatch):
        """With ``PYARROW_IGNORE_TIMEZONE`` set, as importing pandera does,
        pyarrow stores an aware datetime's wall time as UTC. The round-trip
        check sees the shifted instant and leaves the value out."""
        monkeypatch.setenv("PYARROW_IGNORE_TIMEZONE", "1")
        value = dt.datetime(2020, 1, 1, tzinfo=zoneinfo.ZoneInfo("America/New_York"))
        cache = sc.StatCache(tmp_path)
        cache.write("s", {"a": {"ok@1": 7, "v@x": value}})
        got = cache.read("s").values.get("a", {})
        assert got.get("ok@1") == 7
        assert "v@x" not in got, f"{value!r} was cached as {got['v@x']!r}"


# ============================================================
# Stat identity
# ============================================================


class TestStatHashes:
    def test_editing_a_stat_changes_its_hash_and_its_dependents(self, monkeypatch):
        funcs = [low._stat_func, high._stat_func, low_rows._stat_func]
        before = sc.stat_hashes(funcs)
        monkeypatch.setattr(low._stat_func, "source_digest", "edited")
        after = sc.stat_hashes(funcs)
        assert after["low"] != before["low"]
        assert after["low_rows"] != before["low_rows"]
        assert after["high"] == before["high"]

    def test_project_stat_hash_follows_file_content(self, tmp_path):
        from buckaroo.server.xorq_loading import load_project_stat_klasses
        stats_dir = tmp_path / "stats"
        stats_dir.mkdir()
        (stats_dir / "zeros.py").write_text("def compute(col):\n    return (col == 0).sum()\n")
        first = sc.stat_hashes([k._stat_func for k in load_project_stat_klasses(tmp_path)])
        again = sc.stat_hashes([k._stat_func for k in load_project_stat_klasses(tmp_path)])
        (stats_dir / "zeros.py").write_text("def compute(col):\n    return (col == 1).sum()\n")
        edited = sc.stat_hashes([k._stat_func for k in load_project_stat_klasses(tmp_path)])
        assert first == again
        assert edited["zeros"] != first["zeros"]

    def test_every_buckaroo_module_is_part_of_every_stat_hash(self, monkeypatch):
        """A stat's value depends on buckaroo code outside its own file:
        ``histogram`` takes its bucket labels from ``customizations/histogram.py``.
        So every stat hash covers the whole package, and editing any module
        of it invalidates every cached cell."""
        funcs = [obj._stat_func for obj in XORQ_STATS_V2 if hasattr(obj, "_stat_func")]
        before = sc.stat_hashes(funcs)
        edited = Path(histogram_module.__file__)
        real = sc.file_digest
        monkeypatch.setattr(sc, "file_digest", lambda p: "edited" if Path(p) == edited else real(p))
        monkeypatch.setattr(sc, "_ENGINE_CONTEXT", sc._engine_context())
        after = sc.stat_hashes(funcs)
        assert after["histogram"] != before["histogram"]
        assert after["min"] != before["min"]

    @pytest.mark.parametrize("dist", ["pyarrow", "pandas", "numpy"])
    def test_value_conversion_libraries_are_part_of_every_stat_hash(self, dist, monkeypatch):
        """Every value passes through pyarrow, pandas and numpy on its way
        into the accumulator, so their versions are part of every stat hash."""
        before = sc.stat_hashes([low._stat_func])
        real = importlib.metadata.version
        monkeypatch.setattr(importlib.metadata, "version", lambda d: "0.0.0+edited" if d == dist else real(d))
        monkeypatch.setattr(sc, "_ENGINE_CONTEXT", sc._engine_context())
        assert sc.stat_hashes([low._stat_func]) != before

    def test_a_stat_func_takes_its_digest_when_constructed(self, tmp_path):
        """A ``StatFunc`` built directly, without ``@stat``, is keyed by the
        source it was built from. Editing its file afterwards must not lend
        the code still loaded the new file's hash."""
        path = tmp_path / "direct_stat.py"
        path.write_text("def top(col):\n    return col.max()\n")
        spec = importlib.util.spec_from_file_location("direct_stat", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sf = StatFunc("top", module.top, [StatKey("col", XorqColumn)], [StatKey("top", Any)], False)
        before = sc.stat_hashes([sf])
        path.write_text("def top(col):\n    return col.min() + 1\n")
        assert sc.stat_hashes([sf]) == before

    def test_a_partial_is_keyed_by_its_function_and_bound_arguments(self, tmp_path):
        module = _import_file(tmp_path / "partials.py", "def plus(col, n):\n    return col.count() + n\n")
        one = _digest(functools.partial(module.plus, n=1))
        assert one is not None
        assert one != _digest(functools.partial(module.plus, n=2))
        assert one != sc.file_digest(functools.__file__)

    def test_a_partial_of_a_function_with_no_source_file_has_no_digest(self):
        ns: dict = {}
        exec(compile("def plus(col, n):\n    return col.count() + n\n", "<cell>", "exec"), ns)
        assert _digest(functools.partial(ns["plus"], n=1)) is None

    def test_a_closure_is_keyed_by_the_values_it_captures(self, tmp_path):
        module = _import_file(tmp_path / "closures.py",
            "def make_plus(n):\n    def plus(col):\n        return col.count() + n\n    return plus\n")
        assert _digest(module.make_plus(1)) is not None
        assert _digest(module.make_plus(1)) == _digest(module.make_plus(1))
        assert _digest(module.make_plus(1)) != _digest(module.make_plus(2))

    def test_a_callable_object_has_no_digest(self, tmp_path):
        """Its instance state isn't in any file, so its cells are never cached."""
        module = _import_file(tmp_path / "objects.py",
            "class Plus:\n    def __init__(self, n):\n        self.n = n\n\n"
            "    def __call__(self, col):\n        return col.count() + self.n\n")
        assert _digest(module.Plus(1)) is None
        assert _digest(module.Plus(1).__call__) is None

    def test_post_processing_hash_covers_file_name_file_content_and_method(self, tmp_path):
        """A post-processing step is identified by the name of the file that
        defines it, that file's content, and its method name."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        steps = _import_file(tmp_path / "a" / "steps.py", TWO_STEPS_SOURCE)
        renamed = _import_file(tmp_path / "a" / "other_steps.py", TWO_STEPS_SOURCE)
        edited = _import_file(tmp_path / "b" / "steps.py", TWO_STEPS_SOURCE + "# edited\n")
        h = sc.post_processing_hash
        assert h(steps.HighOnly) is not None
        assert h(steps.HighOnly) != h(steps.LowOnly)
        assert h(steps.HighOnly) != h(renamed.HighOnly)
        assert h(steps.HighOnly) != h(edited.HighOnly)


# ============================================================
# Pipeline: additive, column-bisectable, a full hit does no work
# ============================================================


class TestPipelineCache:
    def test_full_hit_builds_no_expressions_and_runs_no_queries(self, tmp_path, monkeypatch):
        cache = sc.StatCache(tmp_path)
        cold, cold_errs = _pipeline(cache).process_table(_table(), scope_id="s")
        calls = _spy_data_touching_calls(monkeypatch, XORQ_STATS_V2)
        with ExecSpy() as spy:
            warm, warm_errs = _pipeline(cache).process_table(_table(), scope_id="s")
        assert spy.queries == []
        assert calls == []
        assert cold_errs == warm_errs == []
        assert warm == cold
        assert type(warm["ints"]["min"]) is int

    def test_added_stat_computes_only_that_stat(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        _pipeline(cache).process_table(_table(), scope_id="s")
        with ExecSpy() as spy:
            sd, errs = _pipeline(cache, XORQ_STATS_V2 + [non_null]).process_table(_table(), scope_id="s")
        assert errs == []
        assert len(spy.queries) == 1
        assert spy.batch_cells() == {(c, "non_null") for c in _table().columns}
        assert sd["ints"]["non_null"] == 40
        assert len(_parts(cache, "s")) == 2

    def test_column_bisect_computes_only_new_columns(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        table = _wide_table()
        cols = list(table.columns)
        for step, (lo, hi) in enumerate([(0, 10), (10, 20), (20, 25)]):
            with ExecSpy() as spy:
                sd, errs = _pipeline(cache).process_table(table, scope_id="s", stat_columns=cols[:hi])
            assert errs == []
            new = set(cols[lo:hi])
            assert len(spy.batch_queries()) == 1
            assert {c for c, _ in spy.batch_cells()} == new
            # One batch aggregate plus one histogram query per new column.
            assert len(spy.queries) == 1 + len(new)
            assert len(_parts(cache, "s")) == step + 1
            assert all(sd[c]["histogram"] for c in cols[:hi])

    def test_editing_a_stat_recomputes_it_and_its_dependents_only(self, tmp_path, monkeypatch):
        cache = sc.StatCache(tmp_path)
        stats = [low, high, low_rows]
        table = _wide_table(3)
        _pipeline(cache, stats).process_table(table, scope_id="s")
        monkeypatch.setattr(low._stat_func, "source_digest", "edited")
        with ExecSpy() as spy:
            sd, errs = _pipeline(cache, stats).process_table(table, scope_id="s")
        assert errs == []
        assert {s for _, s in spy.batch_cells()} == {"low"}
        # low_rows depends on low, so it reruns once per column; high doesn't.
        assert len(spy.queries) == 1 + len(table.columns)

    def test_scope_id_separates_cells(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        _pipeline(cache).process_table(_table(), scope_id=sc.make_scope_id("d1"))
        with ExecSpy() as spy:
            _pipeline(cache).process_table(_table(), scope_id=sc.make_scope_id("d2"))
        assert spy.batch_queries()
        with ExecSpy() as spy:
            _pipeline(cache).process_table(_table(), scope_id=sc.make_scope_id("d1", "pp-hash"))
        assert spy.batch_queries()
        with ExecSpy() as spy:
            _pipeline(cache).process_table(_table(), scope_id=sc.make_scope_id("d1"))
        assert spy.queries == []

    def test_poison_stat_is_isolated_and_its_error_cached(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        stats = XORQ_STATS_V2 + [digits_max]
        sd, errs = _pipeline(cache, stats).process_table(_table(), scope_id="s")
        assert {(e.column, e.stat_key) for e in errs} == {("strs", "digits_max")}
        assert sd["ints"]["digits_max"] == 12
        assert sd["strs"]["null_count"] == 0
        assert sd["ints"]["min"] == 0
        with ExecSpy() as spy:
            _sd, errs2 = _pipeline(cache, stats).process_table(_table(), scope_id="s")
        assert spy.queries == []
        assert {(e.column, e.stat_key) for e in errs2} == {("strs", "digits_max")}

    def test_nothing_is_cached_when_every_query_fails(self, tmp_path, monkeypatch):
        cache = sc.StatCache(tmp_path)

        def backend_down(expr, *args, **kwargs):
            raise ConnectionError("backend down")

        with monkeypatch.context() as m:
            m.setattr(ibis_core.Expr, "execute", backend_down)
            _sd, errs = _pipeline(cache).process_table(_table(), scope_id="s")
        assert errs
        assert _parts(cache, "s") == []
        sd, errs = _pipeline(cache).process_table(_table(), scope_id="s")
        assert errs == []
        assert sd["ints"]["min"] == 0

    @pytest.mark.parametrize("make_err", list(_ENVIRONMENTAL_FAILURES.values()), ids=list(_ENVIRONMENTAL_FAILURES))
    @pytest.mark.parametrize("stat_obj", [queried_rows, queried_rows_or_default], ids=["error", "default"])
    def test_a_query_failing_for_its_environment_is_never_cached(self, tmp_path, monkeypatch, stat_obj, make_err):
        """A per-column query that fails because of where it ran (out of file
        handles, a snapshot file gone, an object store or engine IO error, or
        any error one of those caused) says nothing about the stat, though
        queries before and after it succeeded. Neither its error nor the
        ``default`` standing in for it is cached."""
        cache = sc.StatCache(tmp_path)
        stats = [low, high, stat_obj]
        monkeypatch.setitem(_QUERY_FAILURES, "ints", make_err())
        _pipeline(cache, stats).process_table(_table(), scope_id="s")
        monkeypatch.delitem(_QUERY_FAILURES, "ints")
        sd, errs = _pipeline(cache, stats).process_table(_table(), scope_id="s")
        assert errs == []
        assert sd["ints"][stat_obj.__name__] == 40
        assert sd["floats"][stat_obj.__name__] == 40

    @pytest.mark.parametrize("stat_obj", [queried_rows, queried_rows_or_default], ids=["error", "default"])
    def test_a_query_failing_with_no_query_succeeding_after_it_is_not_cached(self, tmp_path, monkeypatch,
            stat_obj):
        """The backend can go away partway through a run, with an error that
        doesn't name the cause. The batch succeeding earlier doesn't show the
        backend was up for the queries after it: a failure is cached only
        when a query succeeded after it."""
        cache = sc.StatCache(tmp_path)
        stats = [low, high, stat_obj]
        for col in _table().columns:
            monkeypatch.setitem(_QUERY_FAILURES, col, RuntimeError("snapshot unavailable"))
        _pipeline(cache, stats).process_table(_table(), scope_id="s")
        for col in _table().columns:
            monkeypatch.delitem(_QUERY_FAILURES, col)
        sd, errs = _pipeline(cache, stats).process_table(_table(), scope_id="s")
        assert errs == []
        assert sd["ints"][stat_obj.__name__] == 40

    def test_batch_failures_with_no_query_succeeding_after_them_are_not_cached(self, tmp_path, monkeypatch):
        """The batch fails and the ``count()`` canary succeeds, then the
        backend goes away, so isolating the batch fails every stat's own
        aggregate. The canary ran before those failures and doesn't show the
        backend was up for them, so none of them is cached."""
        cache = sc.StatCache(tmp_path)
        real = ibis_core.Expr.execute

        def canary_only(expr, *args, **kwargs):
            if getattr(expr, "schema", None) is None or list(expr.schema().names) != [TOTAL_LENGTH_KEY]:
                raise RuntimeError("snapshot unavailable")
            return real(expr, *args, **kwargs)

        with monkeypatch.context() as m:
            m.setattr(ibis_core.Expr, "execute", canary_only)
            _sd, errs = _pipeline(cache, [low, high]).process_table(_table(), scope_id="s")
        assert errs
        sd, errs = _pipeline(cache, [low, high]).process_table(_table(), scope_id="s")
        assert errs == []
        assert sd["ints"]["low"] == 0

    def test_a_partial_stat_is_keyed_by_its_bound_arguments(self, tmp_path):
        """A stat built from ``functools.partial`` runs its function with the
        bound arguments, so rebinding them recomputes the stat instead of
        serving the value computed with the old ones."""
        module = _import_file(tmp_path / "partials.py", "def plus(col, n):\n    return col.count() + n\n")
        cache = sc.StatCache(tmp_path / "cache")
        for n in (1, 2):
            sf = StatFunc("plus", functools.partial(module.plus, n=n), [StatKey("col", XorqColumn)],
                [StatKey("plus", int)], False)
            sd, errs = _pipeline(cache, [sf]).process_table(_table(), scope_id="s")
            assert errs == []
            assert sd["ints"]["plus"] == 40 + n

    @pytest.mark.parametrize("name", _ddd_params((name, name) for name, _ in _ddd_frames()))
    def test_ddd_frames_load_the_same_warm_as_cold(self, tmp_path, name):
        """A warm load of any DDD frame xorq can load is served entirely from
        the cache and returns exactly the stats the cold load computed, a
        ``ColumnValue`` stat over every column included."""
        table = _ddd_xorq_table(name)
        if table is None:
            pytest.skip(f"xorq can't load {name}")
        cache = sc.StatCache(tmp_path)
        stats = XORQ_STATS_V2 + [first_value]
        cold, cold_errs = _pipeline(cache, stats).process_table(table, scope_id="s")
        warm_pipeline = _pipeline(cache, stats)
        warm, warm_errs = warm_pipeline.process_table(table, scope_id="s")
        assert warm_pipeline.cache_run_stats()["misses"] == 0, "the warm load recomputed cells the cold load wrote"
        assert {(e.column, e.stat_key) for e in warm_errs} == {(e.column, e.stat_key) for e in cold_errs}
        for col, cells in cold.items():
            for key, value in cells.items():
                assert _same(warm[col][key], value), f"{col}.{key}: {value!r} came back as {warm[col][key]!r}"

    def test_a_stat_with_no_source_file_is_never_cached(self, tmp_path):
        """A stat compiled from a string (a notebook cell, ``exec``) has no file
        to hash, and its code object doesn't cover the globals it reads. Its
        cells are computed on every run and never written."""
        ns = {"stat": stat, "XorqColumn": XorqColumn}
        exec(compile("@stat()\ndef twice_count(col: XorqColumn) -> int:\n    return col.count() * 2\n",
            "<cell>", "exec"), ns)
        stats = XORQ_STATS_V2 + [ns["twice_count"]]
        cache = sc.StatCache(tmp_path)
        for _ in range(2):
            with ExecSpy() as spy:
                sd, errs = _pipeline(cache, stats).process_table(_table(), scope_id="s")
            assert errs == []
            assert sd["ints"]["twice_count"] == 80
        assert {s for _, s in spy.batch_cells()} == {"twice_count"}
        names = [n for part in _parts(cache, "s") for n in pq.read_schema(part).names]
        assert not [n for n in names if n.startswith("twice_count@")]

    def test_cache_run_stats_count_cells_and_parts(self, tmp_path):
        cache = sc.StatCache(tmp_path)
        cold = _pipeline(cache)
        cold.process_table(_table(), scope_id="s")
        cs = cold.cache_run_stats()
        assert cs["status"] == "miss"
        assert cs["hits"] == 0 and cs["misses"] > 0
        assert cs["parts_read"] == 0 and cs["parts_written"] == 1
        assert cs["errors_cached"] == 0

        warm = _pipeline(cache)
        warm.process_table(_table(), scope_id="s")
        ws = warm.cache_run_stats()
        assert ws["status"] == "hit"
        assert ws["misses"] == 0 and ws["hits"] == cs["misses"]
        assert ws["parts_read"] == 1 and ws["parts_written"] == 0


# ============================================================
# Dataflow: data_id, post-processing scopes, filtered scopes
# ============================================================


class TestServerDataflowScopes:
    def test_scopes_follow_data_id_and_post_processing(self, tmp_path, monkeypatch):
        from buckaroo import xorq_buckaroo
        from buckaroo.server.xorq_loading import (XorqServerDataflow,
            load_project_post_processing_klasses)
        project = tmp_path / "project"
        (project / "post_processing").mkdir(parents=True)
        (project / "post_processing" / "head_two.py").write_text(
            "def process(expr): return expr.limit(2)\n")
        extra = load_project_post_processing_klasses(project)
        cache_path = tmp_path / "cache"
        scopes_root = cache_path / "parquet" / "v1"

        def load(data_id):
            # A fresh server process: no row counts carried over.
            monkeypatch.setattr(xorq_buckaroo, "_expr_count_cache", type(xorq_buckaroo._expr_count_cache)())
            return XorqServerDataflow(_table(), skip_main_serial=True, extra_klasses=extra,
                cache_storage_path=str(cache_path), data_id=data_id)

        load("d1")
        assert len(list(scopes_root.iterdir())) == 1
        with ExecSpy() as spy:
            load("d1")
        assert spy.queries == []

        with ExecSpy() as spy:
            dataflow = load("d2")
        assert spy.batch_queries()
        assert len(list(scopes_root.iterdir())) == 2

        dataflow.post_processing_method = "head_two"
        assert len(list(scopes_root.iterdir())) == 3
        # A search is part of the scope, so it gets its own.
        dataflow.quick_command_args = {"search": ["s1"]}
        assert len(list(scopes_root.iterdir())) == 4

        dataflow = load("d2")
        with ExecSpy() as spy:
            dataflow.post_processing_method = "head_two"
        assert spy.queries == []

    @staticmethod
    def _load(cache_path, monkeypatch, data_id="d1", extra_klasses=None):
        from buckaroo import xorq_buckaroo
        from buckaroo.server.xorq_loading import XorqServerDataflow
        # A fresh server process: no row counts carried over.
        monkeypatch.setattr(xorq_buckaroo, "_expr_count_cache", type(xorq_buckaroo._expr_count_cache)())
        return XorqServerDataflow(_table(), skip_main_serial=True, cache_storage_path=str(cache_path),
            data_id=data_id, extra_klasses=extra_klasses)

    @staticmethod
    def _length(dataflow, col="strs"):
        return next(v["length"] for v in dataflow.summary_sd.values() if v["orig_col_name"] == col)

    @staticmethod
    def _stat(dataflow, col, key):
        return next(v[key] for v in dataflow.summary_sd.values() if v["orig_col_name"] == col)

    def test_a_cache_key_that_cant_be_computed_falls_back_to_uncached_stats(self, tmp_path, monkeypatch):
        """With no ``data_id`` the scope is keyed by xorq's snapshot hash. When
        that raises, the load computes its stats uncached instead of failing."""
        from buckaroo import xorq_buckaroo

        def no_key(table):
            raise RuntimeError("can't hash this expression")
        monkeypatch.setattr(xorq_buckaroo, "fallback_data_id", no_key)
        dataflow = self._load(tmp_path, monkeypatch, data_id=None)
        assert self._length(dataflow) == 40
        assert self._stat(dataflow, "ints", "max") == 12
        assert not list(tmp_path.glob("parquet/v1/*/part-*.parquet"))

    def test_post_processing_steps_in_one_file_get_their_own_scopes(self, tmp_path, monkeypatch):
        """Two post-processing steps defined in one file share the file, so
        switching from one to the other must still show the second step's
        stats, not the first's."""
        steps = _import_file(tmp_path / "steps.py", TWO_STEPS_SOURCE)
        dataflow = self._load(tmp_path / "cache", monkeypatch, extra_klasses=[steps.HighOnly, steps.LowOnly])
        dataflow.post_processing_method = "high_only"
        assert (self._stat(dataflow, "ints", "min"), self._stat(dataflow, "ints", "max")) == (6, 12)
        dataflow.post_processing_method = "low_only"
        assert (self._stat(dataflow, "ints", "min"), self._stat(dataflow, "ints", "max")) == (0, 4)

    def test_a_search_reads_its_own_cells(self, tmp_path, monkeypatch):
        """A committed search filters the rows the stats run over, so it's part
        of the scope. Over a warm unfiltered scope, the search's stats and
        filtered row count are the 5 matching rows', not all 40."""
        dataflow = self._load(tmp_path, monkeypatch)
        assert self._length(dataflow) == 40
        dataflow.quick_command_args = {"search": ["s1"]}
        assert self._length(dataflow) == 5
        assert dataflow.df_meta["filtered_rows"] == 5
        assert dataflow.df_meta["total_rows"] == 40

    def test_a_search_never_writes_the_unfiltered_scope(self, tmp_path, monkeypatch):
        """A search over a scope with no cells (here, wiped under a live
        session) writes the matching rows' cells under its own scope. The next
        unfiltered load still sees all 40 rows."""
        dataflow = self._load(tmp_path, monkeypatch)
        shutil.rmtree(tmp_path / "parquet")
        dataflow.quick_command_args = {"search": ["s1"]}
        assert self._length(dataflow) == 5
        fresh = self._load(tmp_path, monkeypatch)
        assert self._length(fresh) == 40
        assert fresh.df_meta["total_rows"] == 40

    def test_a_search_scope_is_cached_and_clearing_it_reads_the_warm_scope(self, tmp_path, monkeypatch):
        """A search's scope persists like any other, so the same search in a
        fresh process runs no query. Clearing the search reads the unfiltered
        scope's cells instead of recomputing them."""
        self._load(tmp_path, monkeypatch).quick_command_args = {"search": ["s1"]}
        dataflow = self._load(tmp_path, monkeypatch)
        with ExecSpy() as spy:
            dataflow.quick_command_args = {"search": ["s1"]}
        assert spy.queries == []
        assert self._length(dataflow) == 5
        assert dataflow.df_meta["filtered_rows"] == 5
        assert dataflow.df_meta["total_rows"] == 40
        with ExecSpy() as spy:
            dataflow.quick_command_args = {}
        assert spy.queries == []
        assert self._length(dataflow) == 40
