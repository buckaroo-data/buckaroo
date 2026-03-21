"""Tests that weird-type DataFrames produce correct column configs and histograms
through the full widget pipeline — not just the stat pipeline.

These tests catch regressions where:
- _get_summary_sd discards stats on non-critical errors (returned {} instead of sdf)
- Parquet serialization fails for period/interval/timedelta/binary columns
- v1 TypingStats misclassifies types (Duration→datetime→blank cells)
"""
import base64
import json
from io import BytesIO

import pandas as pd
import polars as pl

from buckaroo.buckaroo_widget import BuckarooWidget, BuckarooInfiniteWidget
from buckaroo.polars_buckaroo import PolarsBuckarooWidget
from buckaroo.ddd_library import df_with_weird_types, pl_df_with_weird_types


def _get_column_configs(bw):
    """Extract main column configs from a widget."""
    return bw.df_display_args['main']['df_viewer_config']['column_config']


def _get_merged_sd(bw):
    """Extract merged_sd from a widget's dataflow."""
    return bw.dataflow.merged_sd


def _resolve_all_stats(all_stats):
    """Resolve all_stats (parquet_b64 or JSON) to list of row dicts."""
    if isinstance(all_stats, list):
        return all_stats
    if isinstance(all_stats, dict) and all_stats.get('format') == 'parquet_b64':
        import pyarrow.parquet as pq
        raw = base64.b64decode(all_stats['data'])
        table = pq.read_table(BytesIO(raw))
        col_names = table.column_names

        if any('__' in c for c in col_names):
            row_dict = table.to_pydict()
            stat_cols = {}
            all_cols = set()
            for key in col_names:
                sep = key.index('__')
                col, stat = key[:sep], key[sep+2:]
                all_cols.add(col)
                if stat not in stat_cols:
                    stat_cols[stat] = {}
                val = row_dict[key][0]
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, (list, dict)):
                            val = parsed
                    except (json.JSONDecodeError, ValueError):
                        pass
                stat_cols[stat][col] = val
            rows = []
            for stat, cols in stat_cols.items():
                row = {'index': stat, 'level_0': stat}
                for c in sorted(all_cols):
                    row[c] = cols.get(c)
                rows.append(row)
            return rows

        df = table.to_pandas()
        rows = json.loads(df.to_json(orient='records'))
        parsed_rows = []
        for row in rows:
            parsed = {}
            for k, v in row.items():
                if k in ('index', 'level_0'):
                    parsed[k] = v
                elif isinstance(v, str):
                    try:
                        parsed[k] = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        parsed[k] = v
                else:
                    parsed[k] = v
            parsed_rows.append(parsed)
        return parsed_rows
    return all_stats


# ============================================================================
# Pandas widget tests
# ============================================================================

class TestPandasWeirdTypesWidget:
    def test_widget_creates_without_error(self):
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        assert bw is not None

    def test_column_configs_not_empty(self):
        """Regression: _get_summary_sd returned {} on histogram errors, producing 0 column configs."""
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        cc = _get_column_configs(bw)
        assert len(cc) == 5

    def test_column_types_correct(self):
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        sd = _get_merged_sd(bw)
        types = {stats['_type'] for stats in sd.values()}
        assert 'categorical' in types
        assert 'duration' in types
        assert 'period' in types
        assert 'interval' in types
        assert 'integer' in types

    def test_displayers_correct(self):
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        cc = _get_column_configs(bw)
        displayers = {c['col_name']: c['displayer_args']['displayer'] for c in cc}
        assert displayers['a'] == 'string'    # categorical
        assert displayers['b'] == 'duration'  # timedelta
        assert displayers['c'] == 'string'    # period
        assert displayers['d'] == 'string'    # interval
        assert displayers['e'] == 'float'     # integer

    def test_histograms_present(self):
        """Regression: histograms were lost when _get_summary_sd returned {} on any error."""
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        sd = _get_merged_sd(bw)
        for col, stats in sd.items():
            h = stats.get('histogram')
            assert h is not None and len(h) > 0, (
                f"Column {col} ({stats['_type']}) missing histogram"
            )

    def test_df_data_dict_has_main_and_all_stats(self):
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        assert 'main' in bw.df_data_dict
        assert 'all_stats' in bw.df_data_dict

    def test_main_data_has_rows(self):
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        main = bw.df_data_dict['main']
        assert len(main) == 5

    def test_all_stats_contains_histogram_row(self):
        bw = BuckarooWidget(df_with_weird_types(), record_transcript=False)
        rows = _resolve_all_stats(bw.df_data_dict['all_stats'])
        histogram_rows = [r for r in rows if r.get('index') == 'histogram']
        assert len(histogram_rows) == 1
        hrow = histogram_rows[0]
        # Every data column should have a non-empty histogram list
        for col_key in ('a', 'b', 'c', 'd', 'e'):
            assert isinstance(hrow.get(col_key), list), (
                f"Column {col_key} histogram missing from all_stats"
            )
            assert len(hrow[col_key]) > 0


class TestPandasInfiniteWeirdTypesWidget:
    def test_infinite_widget_creates_without_error(self):
        bw = BuckarooInfiniteWidget(df_with_weird_types(), record_transcript=False)
        assert bw is not None

    def test_column_configs_not_empty(self):
        bw = BuckarooInfiniteWidget(df_with_weird_types(), record_transcript=False)
        cc = _get_column_configs(bw)
        assert len(cc) == 5

    def test_histograms_present(self):
        bw = BuckarooInfiniteWidget(df_with_weird_types(), record_transcript=False)
        sd = _get_merged_sd(bw)
        for col, stats in sd.items():
            h = stats.get('histogram')
            assert h is not None and len(h) > 0, (
                f"Column {col} ({stats['_type']}) missing histogram"
            )


# ============================================================================
# Polars widget tests
# ============================================================================

class TestPolarsWeirdTypesWidget:
    def test_widget_creates_without_error(self):
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        assert bw is not None

    def test_column_configs_not_empty(self):
        """Regression: _get_summary_sd returned {} when Decimal histogram errored."""
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        cc = _get_column_configs(bw)
        assert len(cc) == 6

    def test_column_types_correct(self):
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        sd = _get_merged_sd(bw)
        types = {stats['_type'] for stats in sd.values()}
        assert 'duration' in types
        assert 'time' in types
        assert 'categorical' in types
        assert 'decimal' in types
        assert 'binary' in types
        assert 'integer' in types

    def test_displayers_correct(self):
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        cc = _get_column_configs(bw)
        displayers = {c['col_name']: c['displayer_args']['displayer'] for c in cc}
        assert displayers['a'] == 'duration'
        assert displayers['b'] == 'string'   # time
        assert displayers['c'] == 'string'   # categorical
        assert displayers['d'] == 'float'    # decimal
        assert displayers['e'] == 'obj'      # binary
        assert displayers['f'] == 'float'    # integer

    def test_histograms_present_for_non_decimal(self):
        """Decimal histogram errors, but all other columns should still have histograms."""
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        sd = _get_merged_sd(bw)
        for col, stats in sd.items():
            if stats['_type'] == 'decimal':
                continue  # Decimal histogram is expected to fail
            h = stats.get('histogram')
            assert h is not None and len(h) > 0, (
                f"Column {col} ({stats['_type']}) missing histogram"
            )

    def test_df_data_dict_has_main_and_all_stats(self):
        """Regression: df_data_dict only had ['empty'] when stats errored."""
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        assert 'main' in bw.df_data_dict
        assert 'all_stats' in bw.df_data_dict

    def test_main_data_has_rows(self):
        bw = PolarsBuckarooWidget(pl_df_with_weird_types(), record_transcript=False)
        main = bw.df_data_dict['main']
        assert len(main) == 5


# ============================================================================
# Normal DF regression — make sure we didn't break existing behavior
# ============================================================================

class TestNormalDFHistogramsNotBroken:
    """Verify histograms still work for normal DataFrames."""

    def test_pandas_normal_df_histograms(self):
        df = pd.DataFrame({'a': range(50), 'b': [f'cat_{i%5}' for i in range(50)]})
        bw = BuckarooWidget(df, record_transcript=False)
        sd = _get_merged_sd(bw)
        for col, stats in sd.items():
            h = stats.get('histogram')
            assert h is not None and len(h) > 0, (
                f"Normal DF column {col} missing histogram"
            )

    def test_polars_normal_df_histograms(self):
        df = pl.DataFrame({'a': list(range(50)), 'b': [f'cat_{i%5}' for i in range(50)]})
        bw = PolarsBuckarooWidget(df, record_transcript=False)
        sd = _get_merged_sd(bw)
        for col, stats in sd.items():
            h = stats.get('histogram')
            assert h is not None and len(h) > 0, (
                f"Normal Polars DF column {col} missing histogram"
            )

    def test_pandas_infinite_normal_df_histograms(self):
        df = pd.DataFrame({'a': range(50), 'b': [f'cat_{i%5}' for i in range(50)]})
        bw = BuckarooInfiniteWidget(df, record_transcript=False)
        sd = _get_merged_sd(bw)
        for col, stats in sd.items():
            h = stats.get('histogram')
            assert h is not None and len(h) > 0, (
                f"Normal Infinite DF column {col} missing histogram"
            )
