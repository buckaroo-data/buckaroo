"""End-to-end tests for XorqBuckarooWidget.

Cover the bits the widget owns on top of XorqStatPipeline /
XorqDfStatsV2: column-name rewriting for the frontend, df_meta from
``expr.count()``, postprocessing registration, and the error fallback
when a postprocessor raises.
"""

from io import BytesIO

import pandas as pd
import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.xorq_buckaroo import (  # noqa: E402
    XorqBuckarooInfiniteWidget, XorqBuckarooWidget)


def _expr():
    return xo.memtable(
        {"price": [12.5, 18.9, 7.4, 22.1, 14.0, 9.9, 31.2, 11.5, 19.8, 50.0], "qty": [1, 2, 1, 3, 2, 4, 1, 2, 5, 9],
         "category": ["a", "b", "a", "c", "b", "b", "c", "a", "b", "c"]})


class TestInstantiation:
    def test_smoke(self):
        XorqBuckarooWidget(_expr())

    def test_df_meta_from_count(self):
        w = XorqBuckarooWidget(_expr())
        assert w.df_meta["columns"] == 3
        assert w.df_meta["filtered_rows"] == 10
        assert w.df_meta["total_rows"] == 10

    def test_columns_rewritten_for_frontend(self):
        """Frontend works in 'a, b, c' space; orig names land in header_name."""
        w = XorqBuckarooWidget(_expr())
        cc = w.df_display_args["main"]["df_viewer_config"]["column_config"]
        rewritten = [(c.get("col_name"), c.get("header_name")) for c in cc]
        assert ("a", "price") in rewritten
        assert ("b", "qty") in rewritten
        assert ("c", "category") in rewritten

    def test_main_data_serialized(self):
        w = XorqBuckarooWidget(_expr())
        rows = w.df_data_dict["main"]
        assert len(rows) == 10
        assert "a" in rows[0]  # rewritten 'price'

    def test_summary_sd_keyed_by_rewritten_name(self):
        w = XorqBuckarooWidget(_expr())
        merged = w.dataflow.merged_sd
        assert "a" in merged
        assert merged["a"]["orig_col_name"] == "price"
        assert merged["a"]["length"] == 10
        assert merged["a"]["min"] == 7.4
        assert merged["a"]["max"] == 50.0


class TestPostProcessing:
    def test_add_processing_registers_and_selects(self):
        w = XorqBuckarooWidget(_expr())

        def big_qty(expr):
            return expr.filter(expr.qty > 2)

        w.add_processing(big_qty)
        assert "big_qty" in w.buckaroo_options["post_processing"]
        assert w.buckaroo_state["post_processing"] == "big_qty"

    def test_filter_pushes_down(self):
        """Stats run on the filtered expr — length and min reflect the filter."""
        w = XorqBuckarooWidget(_expr())

        def big_qty(expr):
            return expr.filter(expr.qty > 2)

        w.add_processing(big_qty)
        merged = w.dataflow.merged_sd
        assert merged["a"]["length"] == 4  # 4 rows have qty > 2
        # min price among rows with qty > 2 is 9.9 (qty=4)
        assert merged["a"]["min"] == 9.9
        assert w.df_meta["filtered_rows"] == 4

    def test_switch_back_to_no_processing(self):
        w = XorqBuckarooWidget(_expr())

        def big_qty(expr):
            return expr.filter(expr.qty > 2)

        w.add_processing(big_qty)
        state = w.buckaroo_state.copy()
        state["post_processing"] = ""
        w.buckaroo_state = state
        assert w.df_meta["filtered_rows"] == 10

    def test_processing_error_renders_error_frame(self):
        w = XorqBuckarooWidget(_expr())

        def bad(expr):
            raise RuntimeError("boom")

        w.add_processing(bad)
        rows = w.df_data_dict["main"]
        assert len(rows) == 1
        # error frame is one column 'err' (rewritten to 'a') with the message
        assert rows[0].get("a") == "boom"
        assert w.df_meta["columns"] == 1
        assert w.df_meta["filtered_rows"] == 1


def _searchable_expr():
    return xo.memtable(
        {"name": ["Alice", "Bob", "Charlie", "Daria", "Eve"], "role": ["admin", "user", "admin", "user", "guest"],
         "score": [10, 20, 30, 40, 50]})


class TestSearch:
    def test_search_filters_via_quick_command_args(self):
        w = XorqBuckarooWidget(_searchable_expr())
        assert w.df_meta["filtered_rows"] == 5
        state = w.buckaroo_state.copy()
        state["quick_command_args"] = {"search": ["admin"]}
        w.buckaroo_state = state
        assert w.df_meta["filtered_rows"] == 2

    def test_search_substring_across_string_columns(self):
        """'li' matches Alice (name) and Charlie (name) — not score."""
        w = XorqBuckarooWidget(_searchable_expr())
        state = w.buckaroo_state.copy()
        state["quick_command_args"] = {"search": ["li"]}
        w.buckaroo_state = state
        assert w.df_meta["filtered_rows"] == 2

    def test_empty_search_clears_filter(self):
        w = XorqBuckarooWidget(_searchable_expr())
        state = w.buckaroo_state.copy()
        state["quick_command_args"] = {"search": ["admin"]}
        w.buckaroo_state = state
        assert w.df_meta["filtered_rows"] == 2
        state = w.buckaroo_state.copy()
        state["quick_command_args"] = {"search": [""]}
        w.buckaroo_state = state
        assert w.df_meta["filtered_rows"] == 5


def _paginated_expr():
    return xo.memtable(
        {"a": [3, 1, 4, 1, 5, 9, 2, 6, 5, 3], "b": ["p", "q", "r", "s", "t", "u", "v", "w", "x", "y"]})


def _capture_send(widget):
    captured: list = []
    widget.send = lambda msg, buffers=None: captured.append((msg, buffers))
    return captured


class TestInfiniteWidget:
    def test_smoke(self):
        XorqBuckarooInfiniteWidget(_paginated_expr())

    def test_main_is_empty_pagination_drives_loading(self):
        """Infinite widgets ship empty df_data_dict.main; data arrives via payload."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        assert w.df_data_dict["main"] == []
        assert w.render_func_name == "BuckarooInfiniteWidget"

    def test_payload_slice_returns_correct_rows(self):
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        w._handle_payload_args({"start": 5, "end": 8})
        assert len(captured) == 1
        msg, bufs = captured[0]
        assert msg["type"] == "infinite_resp"
        assert msg["length"] == 10
        df = pd.read_parquet(BytesIO(bufs[0]))
        assert list(df["index"]) == [5, 6, 7]

    def test_payload_sort_pushes_down(self):
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        sort_key = next(
            k for k, v in w.dataflow.merged_sd.items() if v.get("orig_col_name") == "a")
        captured = _capture_send(w)
        w._handle_payload_args(
            {"start": 0, "end": 4, "sort": sort_key, "sort_direction": "asc"})
        msg, bufs = captured[0]
        df = pd.read_parquet(BytesIO(bufs[0]))
        # 'a' values, sorted ascending: [1, 1, 2, 3]
        assert list(df["a"]) == [1, 1, 2, 3]

    def test_second_request_piggyback(self):
        """Frontend can attach a second slice request; widget sends both."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        w._handle_payload_args(
            {"start": 0, "end": 3, "second_request": {"start": 5, "end": 8}})
        assert len(captured) == 2
        first, second = captured
        assert first[0]["key"]["start"] == 0 and first[0]["key"]["end"] == 3
        assert second[0]["key"]["start"] == 5 and second[0]["key"]["end"] == 8

    def test_search_then_paginate_sees_filtered_count(self):
        """Total length in the response reflects the filter — pushdown end-to-end."""
        w = XorqBuckarooInfiniteWidget(_searchable_expr())
        state = w.buckaroo_state.copy()
        state["quick_command_args"] = {"search": ["admin"]}
        w.buckaroo_state = state
        captured = _capture_send(w)
        w._handle_payload_args({"start": 0, "end": 10})
        msg, bufs = captured[0]
        assert msg["length"] == 2  # only Alice + Charlie match
        df = pd.read_parquet(BytesIO(bufs[0]))
        assert len(df) == 2


class TestInfiniteWindowEdges:
    """Edge cases around the [start, end) request window."""

    def test_partial_window_at_end(self):
        """end > total_rows returns the rows that exist; doesn't error."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        w._handle_payload_args({"start": 8, "end": 20})  # only rows 8, 9 exist
        msg, bufs = captured[0]
        df = pd.read_parquet(BytesIO(bufs[0]))
        assert len(df) == 2
        assert list(df["index"]) == [8, 9]
        assert msg["length"] == 10

    def test_window_past_end_returns_empty(self):
        """start beyond row count returns zero rows, not an error."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        w._handle_payload_args({"start": 50, "end": 60})
        msg, bufs = captured[0]
        df = pd.read_parquet(BytesIO(bufs[0]))
        assert len(df) == 0
        assert msg["length"] == 10  # total is still reported

    def test_index_carries_absolute_offsets_across_pages(self):
        """Each page's index column matches its absolute row offset."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        for start, end in [(0, 3), (3, 6), (6, 9)]:
            w._handle_payload_args({"start": start, "end": end})
        indices = [list(pd.read_parquet(BytesIO(bufs[0]))["index"]) for _, bufs in captured]
        assert indices == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]


class TestInfiniteSort:
    """Sort variants — direction and dtype."""

    def test_sort_descending(self):
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        sort_key = next(
            k for k, v in w.dataflow.merged_sd.items() if v.get("orig_col_name") == "a")
        captured = _capture_send(w)
        w._handle_payload_args(
            {"start": 0, "end": 4, "sort": sort_key, "sort_direction": "desc"})
        df = pd.read_parquet(BytesIO(captured[0][1][0]))
        # 'a' values descending: [9, 6, 5, 5]
        assert list(df["a"]) == [9, 6, 5, 5]

    def test_sort_by_string_column(self):
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        sort_key = next(
            k for k, v in w.dataflow.merged_sd.items() if v.get("orig_col_name") == "b")
        captured = _capture_send(w)
        w._handle_payload_args(
            {"start": 0, "end": 5, "sort": sort_key, "sort_direction": "asc"})
        df = pd.read_parquet(BytesIO(captured[0][1][0]))
        assert list(df["b"]) == ["p", "q", "r", "s", "t"]

    def test_sort_with_offset(self):
        """order_by + limit/offset — the second page of a sorted view."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        sort_key = next(
            k for k, v in w.dataflow.merged_sd.items() if v.get("orig_col_name") == "a")
        captured = _capture_send(w)
        w._handle_payload_args(
            {"start": 5, "end": 10, "sort": sort_key, "sort_direction": "asc"})
        df = pd.read_parquet(BytesIO(captured[0][1][0]))
        # full asc sort: [1,1,2,3,3,4,5,5,6,9]; offset 5 → [4,5,5,6,9]
        assert list(df["a"]) == [4, 5, 5, 6, 9]
        # index column counts from the request offset
        assert list(df["index"]) == [5, 6, 7, 8, 9]

    def test_second_request_skipped_when_sorted(self):
        """Sort path returns one parquet payload; second_request is ignored
        (current behaviour — frontend doesn't piggyback when sorted)."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        sort_key = next(
            k for k, v in w.dataflow.merged_sd.items() if v.get("orig_col_name") == "a")
        captured = _capture_send(w)
        w._handle_payload_args(
            {"start": 0, "end": 3, "sort": sort_key, "sort_direction": "asc",
             "second_request": {"start": 5, "end": 8}})
        assert len(captured) == 1


class TestInfinitePostprocessing:
    """Pagination interacts with add_processing in two ways: an
    expression-returning processor stays lazy (push-down preserved),
    a pandas-returning processor falls back to in-process slicing."""

    def test_filter_processor_paginates_with_pushed_down_count(self):
        """Postprocessor returns a filtered expr; pagination still pushes down."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())

        def big_a(expr):
            return expr.filter(expr.a > 3)

        w.add_processing(big_a)
        captured = _capture_send(w)
        w._handle_payload_args({"start": 0, "end": 10})
        msg, bufs = captured[0]
        # _paginated_expr 'a': [3,1,4,1,5,9,2,6,5,3] — filter > 3 → [4,5,9,6,5] (5 rows)
        assert msg["length"] == 5
        df = pd.read_parquet(BytesIO(bufs[0]))
        assert sorted(df["a"]) == [4, 5, 5, 6, 9]

    def test_pandas_processor_paginates_in_process(self):
        """A processor that materialises to pandas takes the in-process slice
        branch in _execute_window."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())

        def materialise(expr):
            return expr.execute()  # returns a pandas DataFrame

        w.add_processing(materialise)
        captured = _capture_send(w)
        w._handle_payload_args({"start": 4, "end": 7})
        msg, bufs = captured[0]
        df = pd.read_parquet(BytesIO(bufs[0]))
        assert len(df) == 3
        assert list(df["index"]) == [4, 5, 6]
        assert msg["length"] == 10


class TestInfiniteErrorPath:
    def test_unknown_sort_column_emits_error_info(self):
        """Garbage sort key → exception caught, error_info sent, length=0.
        We re-raise after sending so the test sees both."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        with pytest.raises(KeyError):
            w._handle_payload_args(
                {"start": 0, "end": 3, "sort": "no_such_col", "sort_direction": "asc"})
        assert len(captured) == 1
        msg, _bufs = captured[0]
        assert msg["type"] == "infinite_resp"
        assert "error_info" in msg
        assert msg["length"] == 0


class TestLazyPostprocessor:
    """Postprocessing steps must just decorate the expression. No
    materialisation inside the step itself — that would defeat the
    push-down design (stats run on a materialised pandas/arrow object
    rather than against the backend, pagination has nothing to bound)."""

    def _spy_executes(self, monkeypatch):
        """Spy on both pandas (``execute``) and arrow (``to_pyarrow``)
        materialisation paths. A lazy step shouldn't trigger either."""
        from xorq.vendor.ibis.expr.types.core import Expr
        ops: list = []
        original_execute = Expr.execute
        original_to_pyarrow = Expr.to_pyarrow

        def spy_execute(self, *args, **kwargs):
            ops.append(type(self.op()).__name__)
            return original_execute(self, *args, **kwargs)

        def spy_to_pyarrow(self, *args, **kwargs):
            ops.append(type(self.op()).__name__)
            return original_to_pyarrow(self, *args, **kwargs)

        monkeypatch.setattr(Expr, "execute", spy_execute)
        monkeypatch.setattr(Expr, "to_pyarrow", spy_to_pyarrow)
        return ops

    def test_filter_step_does_not_execute(self, monkeypatch):
        """Postprocessor body runs exactly once during registration.
        Spy across that call only — it must record zero executes."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        ops = self._spy_executes(monkeypatch)
        executes_during_step = []

        def big_a(expr):
            executes_during_step.append(len(ops))
            result = expr.filter(expr.a > 3).order_by(expr.a)
            executes_during_step.append(len(ops))
            return result

        w.add_processing(big_a)
        # The step entered and exited with the same execute count.
        before, after = executes_during_step
        assert after - before == 0

    def test_multi_stage_step_stays_lazy(self, monkeypatch):
        """A non-trivial step — filter → mutate → order_by — is still
        purely declarative; no execute fires inside the step body."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        ops = self._spy_executes(monkeypatch)
        executes_during_step = []

        def derive(expr):
            executes_during_step.append(len(ops))
            result = (
                expr.filter(expr.a > 1)
                .mutate(a_squared=expr.a * expr.a)
                .order_by("a"))
            executes_during_step.append(len(ops))
            return result

        w.add_processing(derive)
        before, after = executes_during_step
        assert after - before == 0

        # Pagination still works against the derived expression.
        captured = _capture_send(w)
        w._handle_payload_args({"start": 0, "end": 5})
        msg, bufs = captured[0]
        df = pd.read_parquet(BytesIO(bufs[0]))
        # _paginated_expr 'a': [3,1,4,1,5,9,2,6,5,3] — filter > 1 → 8 rows.
        assert msg["length"] == 8
        # mutate column survives — column names get rewritten to a/b/c, but
        # the merged_sd preserves orig_col_name.
        orig_names = {v["orig_col_name"] for v in w.dataflow.merged_sd.values()}
        assert "a_squared" in orig_names

    def test_lazy_step_paginates_with_bounded_execution(self, monkeypatch):
        """End-to-end: lazy step + paginated request → only count + limit
        executes hit the backend, never a bare table fetch."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())

        def lazy_step(expr):
            return expr.filter(expr.a > 1).order_by(expr.a)

        w.add_processing(lazy_step)

        # Spy starts AFTER registration so we only watch pagination.
        ops = self._spy_executes(monkeypatch)
        captured = _capture_send(w)
        w._handle_payload_args({"start": 2, "end": 5})

        # Exactly one count + one limit; no full-table fetch.
        assert ops == ["CountStar", "Limit"]
        df = pd.read_parquet(BytesIO(captured[0][1][0]))
        assert len(df) == 3


class TestInfiniteBoundedExecution:
    """The PR review's central invariant: the expression stays lazy and
    only ever materialises through bounded ops — ``Limit`` for the row
    window (via ``to_pyarrow`` on the arrow path) or ``CountStar`` for
    the scalar total. A bare materialisation on the underlying Table op
    would fetch the entire dataset and defeat the push-down design."""

    def _make_spy(self, monkeypatch):
        """Spy on every materialisation entry point we use: ``execute``
        for aggregates and ``to_pyarrow`` for the row window. Captures
        the outermost op class so the test can assert plan boundedness."""
        from xorq.vendor.ibis.expr.types.core import Expr
        ops_seen: list = []
        original_execute = Expr.execute
        original_to_pyarrow = Expr.to_pyarrow

        def spy_execute(self, *args, **kwargs):
            ops_seen.append(type(self.op()).__name__)
            return original_execute(self, *args, **kwargs)

        def spy_to_pyarrow(self, *args, **kwargs):
            ops_seen.append(type(self.op()).__name__)
            return original_to_pyarrow(self, *args, **kwargs)

        monkeypatch.setattr(Expr, "execute", spy_execute)
        monkeypatch.setattr(Expr, "to_pyarrow", spy_to_pyarrow)
        return ops_seen

    def test_unsorted_window_only_emits_count_and_limit(self, monkeypatch):
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        captured = _capture_send(w)
        ops = self._make_spy(monkeypatch)
        w._handle_payload_args({"start": 5, "end": 8})
        # Exactly two executes: aggregate (count) + bounded window (limit).
        assert ops == ["CountStar", "Limit"]
        # And the slice respected the bound.
        df = pd.read_parquet(BytesIO(captured[0][1][0]))
        assert len(df) == 3

    def test_sorted_window_only_emits_count_and_limit(self, monkeypatch):
        w = XorqBuckarooInfiniteWidget(_paginated_expr())
        sort_key = next(
            k for k, v in w.dataflow.merged_sd.items() if v.get("orig_col_name") == "a")
        captured = _capture_send(w)
        ops = self._make_spy(monkeypatch)
        w._handle_payload_args(
            {"start": 0, "end": 4, "sort": sort_key, "sort_direction": "asc"})
        # Sort wraps the table in Sort -> Limit; we only execute the Limit
        # (the outermost op), never a bare Table fetch.
        assert ops == ["CountStar", "Limit"]
        assert len(pd.read_parquet(BytesIO(captured[0][1][0]))) == 4

    def test_no_full_table_execute_on_large_expr(self, monkeypatch):
        """Synthesise a 'large' expression and verify the spy never sees a
        bare Table op execute. The expr is small in this test, but the
        same code path handles backends where a bare execute would round-
        trip the entire dataset."""
        big = xo.memtable({"a": list(range(1000))})
        w = XorqBuckarooInfiniteWidget(big)
        ops = self._make_spy(monkeypatch)
        w._handle_payload_args({"start": 100, "end": 110})
        # The processed_df is ``big`` (an InMemoryTable op). A bare
        # ``processed_df.execute()`` would show up here as 'InMemoryTable'.
        assert "InMemoryTable" not in ops
        assert ops == ["CountStar", "Limit"]

    def test_window_uses_arrow_path_no_pandas_detour(self, monkeypatch):
        """Mirror polars infinite: arrow → parquet, no pandas in the wire
        path for the ibis branch.

        Spies on both ``Expr.execute`` and ``Expr.to_pyarrow`` *after*
        widget construction (so registration-time stat queries don't
        pollute the read-out). The windowed slice must travel via
        ``to_pyarrow`` (arrow Table) and never hit ``execute`` (which
        would return a pandas DataFrame)."""
        w = XorqBuckarooInfiniteWidget(_paginated_expr())

        from xorq.vendor.ibis.expr.types.core import Expr
        execute_ops: list = []
        to_pyarrow_ops: list = []
        original_execute = Expr.execute
        original_to_pyarrow = Expr.to_pyarrow

        def spy_execute(self, *args, **kwargs):
            execute_ops.append(type(self.op()).__name__)
            return original_execute(self, *args, **kwargs)

        def spy_to_pyarrow(self, *args, **kwargs):
            to_pyarrow_ops.append(type(self.op()).__name__)
            return original_to_pyarrow(self, *args, **kwargs)

        monkeypatch.setattr(Expr, "execute", spy_execute)
        monkeypatch.setattr(Expr, "to_pyarrow", spy_to_pyarrow)

        w._handle_payload_args({"start": 2, "end": 5})

        # The aggregate (count) goes through .execute() — that's a scalar
        # round-trip, not the wire payload.
        assert execute_ops == ["CountStar"]
        # The row window goes through .to_pyarrow() — never .execute().
        assert to_pyarrow_ops == ["Limit"]
