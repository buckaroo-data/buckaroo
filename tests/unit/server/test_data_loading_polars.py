"""Unit tests for ``buckaroo.server.data_loading_polars``.

Covers behaviour added in PR #855 (``backend='polars'`` for ``/load``)
and pins parity with the pandas path on two edge cases flagged in code
review:

* Search across a frame with no string columns returns 0 rows (matches
  ``search_df_str`` semantics so the UI doesn't appear unfiltered).
* ``.json`` files are read as standard JSON arrays (matches
  ``pd.read_json`` default ``lines=False`` so the same file loads under
  either backend).

It also pins the schema stats tier (rows-first s2) for the pandas and
polars server dataflows side by side: ``stats_tier="schema"`` publishes
the display state full stats give, without reading a value.
"""
import base64
import dataclasses
import datetime
import decimal
import inspect
import io
import json
import os
import tempfile
import threading

import pandas as pd
import polars as pl
import pyarrow.parquet as pq
import pytest
from tornado.ioloop import IOLoop

from buckaroo.dataflow.dataflow import assemble_merged_sd
from buckaroo.dataflow.sd_cache import split_chain_by_scope
from buckaroo.jlisp.lisp_utils import s as lisp_sym
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.pluggable_analysis_framework.stat_units import StatAccumulator, StatState, StatUnit, merge_fragments
from buckaroo.pluggable_analysis_framework.utils import PERVERSE_DF
from buckaroo.server.data_loading import ServerDataflow, handle_infinite_request_buckaroo
from buckaroo.server.data_loading_polars import (PolarsServerDataflow, create_polars_dataflow, handle_infinite_request_buckaroo_polars, load_file_polars)
from buckaroo.server.stat_run import StatCursor, StatRun
from buckaroo.styling_helpers import float_, obj_
from tests.unit.dataflow.scoped_summary_stats_test import (_OverridingPostProcessing, _run_units, _scope_inputs, _scope_sds_by_units)


def _payload(start=0, end=100):
    return {"start": start, "end": end}


def test_search_with_no_string_columns_returns_empty():
    """P1 (#855 codex): non-empty search on a numeric-only frame must
    return 0 rows. The pandas path's ``search_df_str`` OR-accumulates
    matches over string/object columns starting from an all-False mask,
    so a frame with no such columns produces an empty result. The polars
    handler must match — otherwise users see the full frame and assume
    search is broken."""
    df = pl.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
    dataflow = create_polars_dataflow(df)
    msg, _parquet = handle_infinite_request_buckaroo_polars(
        dataflow, _payload(), search_string="anything")
    assert msg["length"] == 0, (
        f"search on numeric-only frame should return 0 rows "
        f"(matching pandas search_df_str), got length={msg['length']}")


def test_search_with_string_columns_still_works():
    """Sanity check the fix doesn't break the happy path: a literal
    substring match on a frame with string columns should still filter
    to matching rows."""
    df = pl.DataFrame({"name": ["alice", "bob", "carol"], "x": [1, 2, 3]})
    dataflow = create_polars_dataflow(df)
    msg, _parquet = handle_infinite_request_buckaroo_polars(
        dataflow, _payload(), search_string="ali")
    assert msg["length"] == 1, f"expected 1 row matching 'ali', got {msg['length']}"


def test_load_file_polars_json_array():
    """P2 (#855 codex): ``.json`` must read a standard JSON array of
    records — matching ``pd.read_json`` default ``lines=False``. The
    initial implementation used ``pl.read_ndjson`` which only accepts
    newline-delimited JSON, so a file that loads fine under
    ``backend='pandas'`` would 500 under ``backend='polars'``."""
    records = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}, {"a": 3, "b": "z"}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(records, f)
        path = f.name
    try:
        df = load_file_polars(path)
        assert df.shape == (3, 2), f"expected (3, 2), got {df.shape}"
        assert sorted(df.columns) == ["a", "b"]
    finally:
        os.unlink(path)


def test_load_file_polars_ndjson_still_works():
    """Newline-delimited JSON should still load — via the ``.ndjson``
    extension. Keeps support for the format the original implementation
    handled, just behind a distinct extension so ``.json`` can mean
    standard JSON (matching pandas)."""
    records = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    with tempfile.NamedTemporaryFile("w", suffix=".ndjson", delete=False) as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        path = f.name
    try:
        df = load_file_polars(path)
        assert df.shape == (2, 2)
    finally:
        os.unlink(path)


def test_load_file_polars_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported file format"):
        load_file_polars("/tmp/foo.xyz")


# ---------------------------------------------------------------------------
# stats_tier="schema" on the pandas and polars server dataflows (rows-first s2)
# ---------------------------------------------------------------------------

_BACKENDS = {
    "pandas": (ServerDataflow, pd.DataFrame, handle_infinite_request_buckaroo),
    "polars": (PolarsServerDataflow, pl.DataFrame, handle_infinite_request_buckaroo_polars)}

# price has a 1e9 maximum, so its estimated column width depends on the min and
# max that only full stats supply.
_TIER_DATA = {
    "price": [12.5, 18.9, 7.4, 22.1, 1e9],
    "qty": [1, 2, 1, 3, 2],
    "category": ["a", "b", "a", "c", "b"]}

# The same columns with a different number of rows per value in every column.
# polars does not keep the order of equal counts, so on _TIER_DATA the mode of
# two full-stats runs over the same frame can differ.
_UNTIED_DATA = {
    "price": [12.5, 12.5, 12.5, 18.9, 18.9, 1e9],
    "qty": [1, 1, 1, 2, 2, 3],
    "category": ["a", "a", "a", "b", "b", "c"]}

# Stats that read values. The schema tier must not publish any of them.
_DATA_STAT_KEYS = {
    "mean", "std", "median", "min", "max", "null_count", "non_null_count",
    "distinct_count", "unique_count", "value_counts", "mode", "histogram",
    "histogram_bins", "memory_usage"}


@pytest.fixture(params=list(_BACKENDS))
def backend(request):
    return request.param


def _frame(backend, data=None):
    return _BACKENDS[backend][1](_TIER_DATA if data is None else data)


def _typed_frame(backend):
    """One column per kind of dtype the typing stats tell apart."""
    days = [datetime.date(2020, 1, 1), datetime.date(2020, 1, 2), datetime.date(2020, 1, 3)]
    if backend == "pandas":
        return pd.DataFrame({
            "float": [1.5, 2.5, 3.5], "int": [1, 2, 3],
            "nullable_int": pd.array([1, None, 3], dtype="Int64"),
            "bool": [True, False, True], "str": ["a", "b", "c"],
            "datetime": pd.to_datetime(days), "datetime_utc": pd.to_datetime(days, utc=True),
            "timedelta": pd.to_timedelta([1, 2, 3], unit="D"),
            "category": pd.Categorical(["a", "b", "a"])})
    return pl.DataFrame({
        "float": [1.5, 2.5, 3.5], "int32": pl.Series([1, 2, 3], dtype=pl.Int32),
        "bool": [True, False, True], "str": ["a", "b", "c"], "date": days,
        "datetime": [datetime.datetime(2020, 1, d) for d in (1, 2, 3)],
        "duration": [datetime.timedelta(days=d) for d in (1, 2, 3)],
        "time": [datetime.time(h) for h in (1, 2, 3)],
        "decimal": pl.Series([decimal.Decimal("1.5")] * 3, dtype=pl.Decimal(10, 2)),
        "binary": [b"a", b"b", b"c"],
        "category": pl.Series(["a", "b", "a"], dtype=pl.Categorical)})


def _build_dataflow(backend, frame=None, **kwargs):
    frame = _frame(backend) if frame is None else frame
    return _BACKENDS[backend][0](frame, skip_main_serial=True, **kwargs)


def _three_scope_dataflow(backend, data=None, **kwargs):
    """A dataflow with a search (filt scope) active and, on pandas, a user op
    (clean scope), so each scope holds its own summary-stats cache entry. The
    polars conf ships no command to run outside a search, so there raw and
    clean are one scope."""
    dataflow = _build_dataflow(backend, _frame(backend, data), **kwargs)
    if backend == "pandas":
        dataflow.operations = [[lisp_sym("fillna"), {"symbol": "df"}, "qty", 0]]
    dataflow.quick_command_args = {"search": ["a"]}
    return dataflow


def _scope_keys(dataflow, tier):
    chains = split_chain_by_scope(dataflow.operations)
    return {scope: dataflow._scope_cache_key(chain, tier=tier) for scope, chain in chains.items()}


def _spy_stat_pipeline(monkeypatch):
    """Record the columns of every frame ``StatPipeline.process_df`` runs on,
    apart from the ``PERVERSE_DF`` its DAG self-check uses, which has no part
    of the loaded data in it."""
    frames = []
    original = StatPipeline.process_df

    def spy(self, df, *args, **kwargs):
        if list(df.columns) != list(PERVERSE_DF.columns):
            frames.append(list(df.columns))
        return original(self, df, *args, **kwargs)

    monkeypatch.setattr(StatPipeline, "process_df", spy)
    return frames


def _without_min_width(column_config):
    return [{**cc, "ag_grid_specs": {k: v for k, v in cc["ag_grid_specs"].items() if k != "minWidth"}}
        for cc in column_config]


def _as_json(sd):
    """Comparable form of an sd: json equates NaN with NaN where == would not."""
    return json.dumps(sd, sort_keys=True, default=str)


def _wire_stat_names(dataflow):
    """The stat names in the ``all_stats`` payload sent to the client."""
    envelope = dataflow.df_data_dict["all_stats"]
    table = pq.read_table(io.BytesIO(base64.b64decode(envelope["data"])))
    return {name.split("__", 1)[1] for name in table.column_names}


def _viewer_config(dataflow, display="main"):
    return dataflow.df_display_args[display]["df_viewer_config"]


class _NoopPostProcessing(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "noop_post"

    @classmethod
    def post_process_df(cls, df):
        return [df, {}]


class TestStatsTierSchema:
    """``stats_tier="schema"`` on ``ServerDataflow`` and
    ``PolarsServerDataflow``: every column is typed from its dtype alone, so
    the dataflow publishes the display state full stats give with no stat
    computed on the data."""

    def test_matches_full_stats_display_state(self, backend):
        full = _build_dataflow(backend)
        schema = _build_dataflow(backend, stats_tier="schema")
        assert schema.df_display_args.keys() == full.df_display_args.keys()
        for name, full_arg in full.df_display_args.items():
            schema_arg = schema.df_display_args[name]
            assert schema_arg["data_key"] == full_arg["data_key"]
            assert schema_arg["summary_stats_key"] == full_arg["summary_stats_key"]
            full_cfg, schema_cfg = full_arg["df_viewer_config"], schema_arg["df_viewer_config"]
            assert schema_cfg["pinned_rows"] == full_cfg["pinned_rows"]
            assert (_without_min_width(schema_cfg["column_config"])
                == _without_min_width(full_cfg["column_config"]))

    def test_host_supplied_pinned_rows_match_full_stats(self, backend):
        """pinned_rows is configuration, so it is the same in every tier even
        when it names a stat the schema tier does not compute."""
        pinned = [obj_("dtype"), float_("mean")]
        full = _build_dataflow(backend, pinned_rows=pinned)
        schema = _build_dataflow(backend, stats_tier="schema", pinned_rows=pinned)
        assert _viewer_config(schema)["pinned_rows"] == _viewer_config(full)["pinned_rows"] == pinned

    def test_min_width_is_the_stats_derived_difference(self, backend):
        widths = {}
        for tier in ("full", "schema"):
            cfg = _viewer_config(_build_dataflow(backend, stats_tier=tier))
            widths[tier] = {cc["header_name"]: cc["ag_grid_specs"]["minWidth"]
                for cc in cfg["column_config"]}
        # price's 1e9 maximum widens it under full stats; without min and max
        # the estimate falls back to a one-digit value.
        assert widths["schema"]["price"] < widths["full"]["price"]

    def test_typing_matches_full_stats_for_every_dtype(self, backend):
        full = _build_dataflow(backend, _typed_frame(backend))
        schema = _build_dataflow(backend, _typed_frame(backend), stats_tier="schema")
        assert schema.merged_sd.keys() == full.merged_sd.keys()
        for col, stats in schema.merged_sd.items():
            assert {"orig_col_name", "rewritten_col_name", "dtype", "_type", "length"} <= stats.keys()
            assert stats == {k: full.merged_sd[col][k] for k in stats}
        assert {"duration", "categorical", "datetime"} <= {
            stats["_type"] for stats in schema.merged_sd.values()}

    def test_publishes_no_data_derived_stat(self, backend):
        full = _build_dataflow(backend)
        schema = _build_dataflow(backend, stats_tier="schema")
        for stats in schema.merged_sd.values():
            assert not _DATA_STAT_KEYS & stats.keys()
        assert _wire_stat_names(schema) == {"dtype"}
        # The same reads on the full tier see the stats, so they would notice.
        assert _DATA_STAT_KEYS & full.merged_sd["a"].keys()
        assert {"dtype", "histogram_bins"} <= _wire_stat_names(full)

    def test_computes_no_stat_on_the_data(self, backend, monkeypatch):
        frames = _spy_stat_pipeline(monkeypatch)
        dataflow = _build_dataflow(backend, stats_tier="schema")
        dataflow.quick_command_args = {"search": ["a"]}
        dataflow.add_analysis(_NoopPostProcessing)
        assert frames == []
        assert "noop_post" in dataflow.buckaroo_options["post_processing"]

    def test_the_spy_sees_the_pipeline_at_the_full_tier(self, backend, monkeypatch):
        frames = _spy_stat_pipeline(monkeypatch)
        _build_dataflow(backend)
        assert frames, "the spy would not notice a stat computed on the data"

    def test_init_sd_hints_and_overrides_still_apply(self, backend):
        dataflow = _build_dataflow(
            backend, stats_tier="schema",
            init_sd={"qty": {"displayer_args": {"displayer": "string", "max_length": 200}}},
            column_config_overrides={
                "category": {"displayer_args": {"displayer": "string", "max_length": 5000}}})
        by_header = {cc["header_name"]: cc for cc in _viewer_config(dataflow)["column_config"]}
        assert by_header["qty"]["displayer_args"]["max_length"] == 200
        assert by_header["category"]["displayer_args"]["max_length"] == 5000

    def test_skipped_column_keeps_init_sd_typing(self, backend):
        """A column in ``skip_stat_columns`` gets only its names from the
        pipeline, so its ``_type`` comes from ``init_sd``. The schema tier
        must not layer the dtype-derived typing keys over it."""
        kwargs = {
            "init_sd": {"qty": {"_type": "float", "mean": 1.8, "min": 1, "max": 3}},
            "skip_stat_columns": ["qty"]}
        full = _build_dataflow(backend, **kwargs)
        schema = _build_dataflow(backend, stats_tier="schema", **kwargs)

        def merged(dataflow, orig_col):
            return next(v for v in dataflow.merged_sd.values() if v["orig_col_name"] == orig_col)

        assert merged(full, "qty")["_type"] == "float"
        assert merged(schema, "qty")["_type"] == "float"
        assert not {"is_numeric", "is_integer", "is_float", "dtype"} & merged(schema, "qty").keys()
        assert merged(schema, "price")["_type"] == "float"
        assert merged(schema, "price")["is_float"] is True
        assert (_without_min_width(_viewer_config(schema)["column_config"])
            == _without_min_width(_viewer_config(full)["column_config"]))

    def test_empty_frame_matches_full_stats(self, backend):
        """Full stats publish nothing for a frame with no rows (the pipeline
        returns an empty summary), so the schema tier does the same."""
        empty = {"x": [], "y": []}
        full = _build_dataflow(backend, _frame(backend, empty))
        schema = _build_dataflow(backend, _frame(backend, empty), stats_tier="schema")
        assert full.merged_sd == {}
        assert schema.merged_sd == {}
        assert schema.df_display_args == full.df_display_args

    def test_sorted_infinite_request_works(self, backend):
        dataflow = _build_dataflow(backend, stats_tier="schema")
        qty = next(k for k, v in dataflow.merged_sd.items() if v["orig_col_name"] == "qty")
        handler = _BACKENDS[backend][2]
        resp, parquet = handler(dataflow, {"start": 0, "end": 5, "sourceName": "default",
            "sort": qty, "sort_direction": "desc"})
        assert "error_info" not in resp
        assert resp["length"] == 5
        assert pq.read_table(io.BytesIO(parquet)).column(qty).to_pylist() == [3, 2, 2, 1, 1]

    def test_pending_state_writes_no_full_tier_cache_key(self, backend):
        dataflow = _three_scope_dataflow(backend, stats_tier="schema")
        full_keys = set(_scope_keys(dataflow, "full").values())
        assert len(full_keys) == (3 if backend == "pandas" else 2)
        assert dataflow.summary_stats_cache
        assert not full_keys & dataflow.summary_stats_cache.keys()

    def test_later_full_assignment_reaches_merged_sd_for_all_scopes(self, backend):
        full = _three_scope_dataflow(backend, _UNTIED_DATA)
        dataflow = _three_scope_dataflow(backend, _UNTIED_DATA, stats_tier="schema")
        assert "mean" not in dataflow.merged_sd["a"]
        assert {"mean", "filtered_mean"} <= full.merged_sd["a"].keys()

        dataflow.stats_tier = "full"
        dataflow.summary_sd = full.summary_sd

        assert _as_json(dataflow.merged_sd) == _as_json(full.merged_sd)

    def test_full_scope_sds_cached_first_are_used_without_the_pipeline(self, backend, monkeypatch):
        full = _three_scope_dataflow(backend)
        dataflow = _three_scope_dataflow(backend, stats_tier="schema")
        cache = dict(dataflow.summary_stats_cache)
        for scope, key in _scope_keys(dataflow, "full").items():
            cache[key] = full.summary_stats_cache[getattr(full, f"{scope}_sd_key")]
        dataflow.summary_stats_cache = cache
        frames = _spy_stat_pipeline(monkeypatch)

        dataflow.stats_tier = "full"
        dataflow.summary_sd = full.summary_sd

        assert frames == []
        assert _as_json(dataflow.merged_sd) == _as_json(full.merged_sd)

    def test_assembled_sd_equals_merged_sd_with_init_sd_and_a_user_op(self, backend):
        # init_sd is keyed by the original column name; price is rewritten to "a".
        dataflow = _three_scope_dataflow(backend, stats_tier="schema", init_sd={
            "price": {"displayer_args": {"displayer": "string", "max_length": 99}, "init_only": 1}})
        sd = dataflow.merged_sd["a"]
        assert sd["init_only"] == 1, "init_sd must reach merged_sd under the rewritten name"
        assert "filtered_length" in sd, "the filter layer must be active"
        if backend == "pandas":
            assert "cleaned_length" in sd, "the cleaning layer must be active"

        assembled = assemble_merged_sd(**_scope_inputs(dataflow))

        assert _as_json(assembled) == _as_json(dataflow.merged_sd)


def test_object_column_is_typed_as_a_string_at_the_schema_tier():
    """pandas gives an object column no dtype to tell strings from other
    values, and calls an empty one a string, so the schema tier types every
    object column as one. Full stats read the values and call the mixed column
    ``obj``; the gap closes when full stats arrive."""
    def frame():
        return pd.DataFrame({
            "words": pd.Series(["a", "b", "c"], dtype=object),
            "mixed": pd.Series([1, "b", 2.5], dtype=object)})

    types = {}
    for tier in ("full", "schema"):
        sd = ServerDataflow(frame(), skip_main_serial=True, stats_tier=tier).merged_sd
        types[tier] = {v["orig_col_name"]: v["_type"] for v in sd.values()}
    assert types["full"] == {"words": "string", "mixed": "obj"}
    assert types["schema"] == {"words": "string", "mixed": "string"}


# ---------------------------------------------------------------------------
# Resumable stat units on the pandas and polars server dataflows (rows-first s4)
# ---------------------------------------------------------------------------


class TestStatUnits:
    """``plan`` and ``run`` on the stats class a dataflow builds, in place of
    the all-at-once constructor."""

    def test_build_stats_without_running_computes_nothing(self, backend, monkeypatch):
        dataflow = _build_dataflow(backend)
        frames = _spy_stat_pipeline(monkeypatch)
        stats = dataflow.build_stats(dataflow.processed_df, run=False)
        stats.plan(stats.state)
        assert frames == []
        assert stats.sdf == {} and stats.errs == {}

    def test_the_default_run_goes_through_the_units(self, backend, monkeypatch):
        """Every column the constructor computes is computed inside a unit, so
        the inline path and a caller running units one at a time cannot
        differ. (The DAG self-check runs ``PERVERSE_DF`` through the same
        units, which has no part of the loaded data in it.)"""
        depth, inside, outside, unit_columns = [0], [], [], []
        original_run, original_column = StatPipeline.run, StatPipeline.process_column

        def spy_run(self, unit, acc):
            depth[0] += 1
            if list(acc.state.data.columns) != list(PERVERSE_DF.columns):
                unit_columns.append(unit.columns)
            try:
                return original_run(self, unit, acc)
            finally:
                depth[0] -= 1

        def spy_column(self, *args, **kwargs):
            (inside if depth[0] else outside).append(kwargs.get("column_name"))
            return original_column(self, *args, **kwargs)

        monkeypatch.setattr(StatPipeline, "run", spy_run)
        monkeypatch.setattr(StatPipeline, "process_column", spy_column)
        _three_scope_dataflow(backend)
        assert {c for cols in unit_columns for c in cols} == {"price", "qty", "category"}
        assert inside and outside == [], "a column's stats ran outside a unit"

    def test_units_assembled_equal_merged_sd_with_init_sd_cleaning_and_overrides(self, backend):
        """The fragments of each scope's units, assembled by
        ``assemble_merged_sd`` with ``init_sd``, a cleaning op (pandas), a
        search filter and a post-processing override, are the dataflow's own
        ``merged_sd``. init_sd is keyed by the original name; price is "a"."""
        dataflow = _three_scope_dataflow(backend, _UNTIED_DATA, init_sd={
            "price": {"displayer_args": {"displayer": "string", "max_length": 99}, "init_only": 1}},
            column_config_overrides={"category": {"displayer_args": {"displayer": "string", "max_length": 5000}}})
        dataflow.add_analysis(_OverridingPostProcessing)
        dataflow.post_processing_method = "override_post"
        sd = dataflow.merged_sd
        assert sd["a"]["init_only"] == 1 and sd["b"]["from_post"] == 1 and sd["b"]["mean"] == 99.5
        assert "filtered_length" in sd["a"], "the filter layer must be active"
        if backend == "pandas":
            assert "cleaned_length" in sd["a"], "the cleaning layer must be active"

        sds = _scope_sds_by_units(dataflow)
        inputs = _scope_inputs(dataflow)
        assembled = assemble_merged_sd(init_sd=inputs["init_sd"], cleaned_sd=inputs["cleaned_sd"], raw_sd=sds["raw"],
            processed_sd=inputs["processed_sd"], processed_df=inputs["processed_df"], chains=inputs["chains"],
            clean_sd=sds["clean"], filt_sd=sds["filt"])

        assert _as_json(assembled) == _as_json(dataflow.merged_sd)

    def test_a_column_group_request_returns_only_those_columns(self, backend):
        dataflow = _build_dataflow(backend, _frame(backend, _UNTIED_DATA))
        stats = dataflow.build_stats(dataflow.processed_df, run=False)
        for names in (("qty", "category"), ("b", "c")):  # original or rewritten names
            state = dataclasses.replace(stats.state, columns=names)
            acc = stats.new_accumulator(state)
            fragments = [stats.run(unit, acc) for unit in stats.plan(state)]
            assert [list(f) for f in fragments] == [["qty"], ["category"]]
            assert list(acc.sd()) == ["qty", "category"]

    def test_skip_stat_columns_get_no_unit(self, backend):
        dataflow = _build_dataflow(backend, _frame(backend, _UNTIED_DATA), skip_stat_columns=["qty"],
            init_sd={"qty": {"_type": "float"}})
        stats = dataflow.build_stats(dataflow.processed_df, run=False)
        assert stats.state.skip_columns == {"qty"}
        assert [u.columns for u in stats.plan(stats.state)] == [("price",), ("category",)]
        acc, fragments = _run_units(stats)
        assert all("qty" not in f for f in fragments)
        assert set(acc.sd()) == {"price", "qty", "category"}


def _stat_run(backend, gen=4):
    dataflow = _build_dataflow(backend, _frame(backend, _UNTIED_DATA))
    return StatRun(gen, "raw", dataflow.build_stats(dataflow.processed_df, run=False)), dataflow


# Original names that are also rewritten names of other columns: the rewritten
# names are c -> a, b -> b, a -> c.
_PERMUTED_DATA = {
    "c": [12.5, 12.5, 12.5, 18.9, 18.9, 1e9],
    "b": [1, 1, 1, 2, 2, 3],
    "a": ["a", "a", "a", "b", "b", "c"]}


def _permuted_stat_run(backend, gen=4):
    dataflow = _build_dataflow(backend, _frame(backend, _PERMUTED_DATA))
    return StatRun(gen, "raw", dataflow.build_stats(dataflow.processed_df, run=False)), dataflow


class TestStatRun:
    """The run a session holds for one generation and scope: the planned
    units, the fragments they produced in the order they finished, and the
    accumulator the units read. It runs a unit only when asked."""

    def test_a_run_is_keyed_by_generation_and_scope_and_plans_its_units(self, backend):
        run, _dataflow = _stat_run(backend)
        assert run.key == (4, "raw")
        assert run.status == "pending" and run.remaining == 3
        assert [u.columns for u in run.units] == [("price",), ("qty",), ("category",)]
        assert run.fragments == [] and run.ran == []

    def test_fragments_are_appended_in_completion_order(self, backend):
        run, _dataflow = _stat_run(backend)
        while True:
            before = list(run.fragments)
            fragment = run.run_next(prefer=("category",))
            if fragment is None:
                break
            assert run.fragments[:-1] == before, "nothing already in the list changes"
            assert run.fragments[-1] is fragment
        assert [list(f) for f in run.fragments] == [["category"], ["price"], ["qty"]]
        assert len(run.ran) == 3 and len(set(run.ran)) == 3

    def test_prefer_runs_the_units_that_name_those_columns_first(self, backend):
        run, _dataflow = _stat_run(backend)
        assert run.next_unit().columns == ("price",)
        assert run.next_unit(prefer=("c",)).columns == ("category",), "a rewritten name works too"
        assert run.next_unit(prefer=("nothing",)).columns == ("price",)

    def test_prefer_reads_a_name_that_is_an_original_name_as_that_column(self, backend):
        """"a" is the original name of the last column and the rewritten name
        of the first. Read once, as the original name, it picks the last."""
        run, _dataflow = _permuted_stat_run(backend)
        assert [u.columns for u in run.units] == [("c",), ("b",), ("a",)]
        assert run.next_unit(prefer=("a",)).columns == ("a",)
        assert run.next_unit(prefer=("b",)).columns == ("b",)
        assert run.next_unit(prefer=("c",)).columns == ("c",)

    def test_prefer_in_the_rewritten_namespace_reads_a_client_s_names(self, backend):
        """A client knows only the rewritten names: its "c" is the column
        whose original name is "a"."""
        run, _dataflow = _permuted_stat_run(backend)
        assert run.next_unit(prefer=("c",), namespace="rewritten").columns == ("a",)
        assert run.next_unit(prefer=("a",), namespace="rewritten").columns == ("c",)
        assert run.next_unit(prefer=("zzz",), namespace="rewritten").columns == ("c",)

    def test_run_next_runs_the_unit_prefer_picks_in_its_namespace(self, backend):
        run, _dataflow = _permuted_stat_run(backend)
        assert list(run.run_next(prefer=("c",), namespace="rewritten")) == ["a"]
        assert list(run.run_next(prefer=("c",))) == ["c"]
        assert run.ran == ["column:a", "column:c"]

    def test_prefer_with_an_unknown_namespace_is_an_error(self, backend):
        run, _dataflow = _permuted_stat_run(backend)
        with pytest.raises(ValueError, match="namespace"):
            run.next_unit(prefer=("c",), namespace="both")

    def test_the_run_is_complete_when_no_unit_is_left(self, backend):
        run, _dataflow = _stat_run(backend)
        while run.run_next() is not None:
            pass
        assert (run.status, run.remaining) == ("complete", 0)
        assert run.next_unit() is None and run.run_next() is None
        assert len(run.fragments) == 3, "asking again runs nothing"

    def test_the_accumulator_holds_what_the_fragments_hold(self, backend):
        run, _dataflow = _stat_run(backend)
        while run.run_next() is not None:
            pass
        assert merge_fragments(run.fragments) == run.acc.sd()

    def test_raw_sd_is_the_full_stats_summary_sd(self, backend):
        run, dataflow = _stat_run(backend)
        while run.run_next() is not None:
            pass
        assert _as_json(run.raw_sd()) == _as_json(dataflow.summary_sd)

    def test_cursors_read_one_list_each_at_its_own_pace(self, backend):
        run, _dataflow = _stat_run(backend)
        a, b = StatCursor(), StatCursor()
        run.run_next()
        run.run_next()
        first_a = a.take(run)
        assert len(first_a) == 2 and a.take(run) == [] and a.caught_up(run)
        run.run_next()
        assert not a.caught_up(run) and b.position == 0, "one cursor's reads move no other"
        all_b = b.take(run)
        rest_a = a.take(run)
        assert (len(all_b), len(rest_a)) == (3, 1)
        assert merge_fragments(first_a + rest_a) == merge_fragments(all_b)
        assert len(set(run.ran)) == 3, "no unit ran twice"

    def test_a_cursor_starts_again_on_another_run(self, backend):
        first, _dataflow = _stat_run(backend, gen=1)
        second, _dataflow = _stat_run(backend, gen=2)
        first.run_next()
        second.run_next()
        second.run_next()
        cursor = StatCursor()
        assert len(cursor.take(first)) == 1
        assert len(cursor.take(second)) == 2, "a position in one run means nothing in another"

    def test_a_run_has_no_thread_timer_or_callback(self, backend, monkeypatch):
        scheduled = []
        monkeypatch.setattr(threading.Thread, "start", lambda self, *a, **k: scheduled.append("thread"))
        for name in ("add_callback", "call_later", "call_at", "add_timeout"):
            monkeypatch.setattr(IOLoop, name, lambda self, *a, _n=name, **k: scheduled.append(_n))
        threads_before = threading.active_count()
        run, _dataflow = _stat_run(backend)
        while run.run_next() is not None:
            pass
        assert scheduled == [] and threading.active_count() == threads_before
        assert not [name for name, value in vars(run).items()
            if isinstance(value, (threading.Thread, threading.Timer)) or inspect.isroutine(value)]

    def test_a_unit_that_raises_fails_the_run(self):

        class _FailingStats:
            state = StatState(data=None)

            def plan(self, state):
                return [StatUnit("one", ("x",), "column"), StatUnit("two", ("y",), "column")]

            def new_accumulator(self, state):
                return StatAccumulator(state, columns=["x", "y"])

            def run(self, unit, acc):
                if unit.id == "two":
                    raise RuntimeError("boom")
                return {"x": {"v": 1}}

        run = StatRun(1, "raw", _FailingStats())
        run.run_next()
        with pytest.raises(RuntimeError, match="boom"):
            run.run_next()
        assert run.status == "error" and isinstance(run.error, RuntimeError)
        assert run.run_next() is None, "a failed run is not retried"
        assert run.fragments == [{"x": {"v": 1}}]
