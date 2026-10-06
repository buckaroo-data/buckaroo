"""Tests for the per-cell summary-stat cache (ADR-001).

A cell is one ``(column, stat)`` value, keyed by ``(scope_id, col, stat_hash)``.
These tests assert structure (which queries run, which cells are computed,
which parts are written), not wall-clock time.
"""

import importlib.metadata
import importlib.util
import math
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

xo = pytest.importorskip("xorq.api")

import xorq.vendor.ibis.expr.types.core as ibis_core  # noqa: E402

import buckaroo.customizations.histogram as histogram_module  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402
from buckaroo.pluggable_analysis_framework import stat_cache as sc  # noqa: E402
from buckaroo.pluggable_analysis_framework.stat_func import (  # noqa: E402
    StatFunc, StatKey, XorqColumn, XorqExecute, XorqExpr, stat)
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline  # noqa: E402


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
def low_rows(expr: XorqExpr, execute: XorqExecute, orig_col_name: str, low: int) -> int:
    """A per-column query stat that depends on ``low``."""
    return int(execute(expr.filter(expr[orig_col_name] == low).count()))


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
        # A search filter makes a filtered scope, which isn't persisted.
        dataflow.quick_command_args = {"search": ["s1"]}
        assert len(list(scopes_root.iterdir())) == 3

        dataflow = load("d2")
        with ExecSpy() as spy:
            dataflow.post_processing_method = "head_two"
        assert spy.queries == []

    @staticmethod
    def _load(cache_path, monkeypatch, data_id="d1"):
        from buckaroo import xorq_buckaroo
        from buckaroo.server.xorq_loading import XorqServerDataflow
        # A fresh server process: no row counts carried over.
        monkeypatch.setattr(xorq_buckaroo, "_expr_count_cache", type(xorq_buckaroo._expr_count_cache)())
        return XorqServerDataflow(_table(), skip_main_serial=True, cache_storage_path=str(cache_path),
            data_id=data_id)

    @staticmethod
    def _length(dataflow, col="strs"):
        return next(v["length"] for v in dataflow.summary_sd.values() if v["orig_col_name"] == col)

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
