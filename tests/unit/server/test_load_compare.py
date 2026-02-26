import json
import os
import sys
import tempfile

import pandas as pd
import pytest
import tornado.testing

from buckaroo.server.app import make_app as _make_app

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Temp file locking prevents cleanup on Windows",
)


def make_app():
    return _make_app(open_browser=False)


def _write_df(df, path):
    ext = os.path.splitext(path)[1]
    if ext == ".csv":
        df.to_csv(path, index=False)
    elif ext == ".parquet":
        df.to_parquet(path, index=False)
    else:
        raise ValueError(f"Unsupported: {ext}")


class TestLoadCompare(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def _post_compare(self, body):
        return self.fetch(
            "/load_compare",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )

    def test_basic_compare(self):
        df1 = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"], "val": [10, 20, 30]})
        df2 = pd.DataFrame({"id": [1, 2, 4], "name": ["a", "B", "d"], "val": [10, 99, 40]})

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-1",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["id"],
                })
                self.assertEqual(resp.code, 200)
                body = json.loads(resp.body)
                self.assertEqual(body["session"], "cmp-1")
                self.assertIn("eqs", body)
                self.assertIn("rows", body)
                self.assertIn("columns", body)
                self.assertEqual(body["rows"], 4)
                self.assertIn("id", body["eqs"])
                self.assertEqual(body["eqs"]["id"]["diff_count"], "join_key")
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)

    def test_column_config_overrides_applied(self):
        """Verify that diff styling (hidden cols, color_map, tooltip) is in the session."""
        df1 = pd.DataFrame({"id": [1, 2], "score": [100, 200]})
        df2 = pd.DataFrame({"id": [1, 2], "score": [100, 999]})

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-style",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["id"],
                })
                self.assertEqual(resp.code, 200)

                sessions = self._app.settings["sessions"]
                session = sessions.get("cmp-style")
                self.assertIsNotNone(session)

                cc = session.df_display_args["main"]["df_viewer_config"]["column_config"]
                cc_by_header = {e["header_name"]: e for e in cc}

                score_entry = cc_by_header["score"]
                self.assertIn("color_map_config", score_entry)
                self.assertIn("tooltip_config", score_entry)
                self.assertNotEqual(score_entry["color_map_config"]["val_column"], "score|eq")

                self.assertEqual(cc_by_header["score|df2"]["merge_rule"], "hidden")
                self.assertEqual(cc_by_header["score|eq"]["merge_rule"], "hidden")
                self.assertEqual(cc_by_header["membership"]["merge_rule"], "hidden")
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)

    def test_compare_session_includes_histograms(self):
        """Compare route should use buckaroo mode so summary stats include histograms."""
        df1 = pd.DataFrame({"id": [1, 2, 3, 4, 5], "v": [10, 20, 30, 40, 50]})
        df2 = pd.DataFrame({"id": [1, 2, 3, 4, 5], "v": [10, 22, 31, 39, 50]})

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-hist",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["id"],
                })
                self.assertEqual(resp.code, 200)

                session = self._app.settings["sessions"].get("cmp-hist")
                self.assertIsNotNone(session)
                self.assertEqual(session.mode, "buckaroo")

                all_stats = session.df_data_dict.get("all_stats", [])
                all_stat_indexes = {
                    row.get("index")
                    for row in all_stats
                    if isinstance(row, dict) and "index" in row
                }
                self.assertIn("histogram", all_stat_indexes)
                self.assertIn("histogram_bins", all_stat_indexes)
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)

    def test_eqs_reports_diffs(self):
        df1 = pd.DataFrame({"k": [1, 2], "v": [10, 20]})
        df2 = pd.DataFrame({"k": [1, 2], "v": [10, 99]})

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-eqs",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["k"],
                })
                self.assertEqual(resp.code, 200)
                body = json.loads(resp.body)
                self.assertEqual(body["eqs"]["v"]["diff_count"], 1)
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)

    def test_missing_fields(self):
        resp = self._post_compare({"session": "x", "path1": "/a"})
        self.assertEqual(resp.code, 400)

    def test_missing_file(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1:
            _write_df(pd.DataFrame({"id": [1]}), f1.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-miss",
                    "path1": f1.name,
                    "path2": "/nonexistent.csv",
                    "join_columns": ["id"],
                })
                self.assertEqual(resp.code, 404)
            finally:
                os.unlink(f1.name)

    def test_bad_json(self):
        resp = self.fetch(
            "/load_compare",
            method="POST",
            body="not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.code, 400)

    def test_duplicate_join_keys(self):
        df1 = pd.DataFrame({"id": [1, 1], "v": [10, 20]})
        df2 = pd.DataFrame({"id": [1, 2], "v": [10, 30]})

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-dup",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["id"],
                })
                self.assertEqual(resp.code, 400)
                body = json.loads(resp.body)
                self.assertEqual(body["error_code"], "compare_error")
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)

    def test_parquet_files(self):
        df1 = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
        df2 = pd.DataFrame({"id": [1, 2], "val": [10, 99]})

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-pq",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["id"],
                })
                self.assertEqual(resp.code, 200)
                body = json.loads(resp.body)
                self.assertEqual(body["rows"], 2)
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)

    def test_how_inner_join(self):
        df1 = pd.DataFrame({"id": [1, 2, 3], "v": [10, 20, 30]})
        df2 = pd.DataFrame({"id": [2, 3, 4], "v": [20, 99, 40]})

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f2:
            _write_df(df1, f1.name)
            _write_df(df2, f2.name)
            try:
                resp = self._post_compare({
                    "session": "cmp-inner",
                    "path1": f1.name,
                    "path2": f2.name,
                    "join_columns": ["id"],
                    "how": "inner",
                })
                self.assertEqual(resp.code, 200)
                body = json.loads(resp.body)
                self.assertEqual(body["rows"], 2)
            finally:
                os.unlink(f1.name)
                os.unlink(f2.name)
