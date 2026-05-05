"""End-to-end tests for XorqBuckarooWidget.

Cover the bits the widget owns on top of XorqStatPipeline /
XorqDfStatsV2: column-name rewriting for the frontend, df_meta from
``expr.count()``, postprocessing registration, and the error fallback
when a postprocessor raises.
"""

import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.xorq_buckaroo import XorqBuckarooWidget  # noqa: E402


def _expr():
    return xo.memtable(
        {
            "price": [12.5, 18.9, 7.4, 22.1, 14.0, 9.9, 31.2, 11.5, 19.8, 50.0],
            "qty": [1, 2, 1, 3, 2, 4, 1, 2, 5, 9],
            "category": ["a", "b", "a", "c", "b", "b", "c", "a", "b", "c"],
        })


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
