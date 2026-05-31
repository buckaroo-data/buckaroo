"""categorical_histogram correctness for the PAF / ColumnExecutor path.

This previously diagnosed differences between the (removed) v1
PolarsAnalysisPipeline and the PAF/ColumnExecutor path. The v1 pipeline is
gone; these assert the ColumnExecutor path — the production polars stat path —
directly.
"""
import polars as pl
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PlTyping, BasicAnalysis, HistogramAnalysis,
    ComputedDefaultSummaryStats)
from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
from buckaroo.file_cache.base import FileCache

HA_CLASSES = [VCAnalysis, PlTyping, BasicAnalysis, ComputedDefaultSummaryStats, HistogramAnalysis]


def _paf_cat_hist(df, col='a'):
    ced = ColumnExecutorDataflow(df.lazy(), analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    return ced.merged_sd.get(col, {}).get('categorical_histogram', {})


def test_simple_categorical_three_values():
    """Three categories with different frequencies."""
    df = pl.DataFrame({'cat_col': ['A'] * 50 + ['B'] * 30 + ['C'] * 20})
    cat_hist = _paf_cat_hist(df)
    assert cat_hist == {'A': 0.5, 'B': 0.3, 'C': 0.2, 'longtail': 0.0, 'unique': 0.0}


def test_categorical_with_longtail():
    """Many unique values create a longtail bucket."""
    frequent = ['A'] * 30 + ['B'] * 20 + ['C'] * 15 + ['D'] * 10 + ['E'] * 8 + ['F'] * 7 + ['G'] * 6
    unique_vals = [f'unique_{i}' for i in range(4)]
    df = pl.DataFrame({'cat_col': frequent + unique_vals})
    cat_hist = _paf_cat_hist(df)
    assert 'longtail' in cat_hist
    assert 'unique' in cat_hist


def test_categorical_mixed_frequencies():
    """The data from the old test_histogram_analysis: foo/bar dominant, rest longtail/unique."""
    cats = [chr(x) for x in range(97, 102)] * 2
    cats += [chr(x) for x in range(103, 113)]
    cats += ['foo'] * 30 + ['bar'] * 50
    df = pl.DataFrame({'categories': cats})
    cat_hist = _paf_cat_hist(df)
    assert cat_hist == {'bar': 0.5, 'foo': 0.3, 'longtail': 0.1, 'unique': 0.1}


def test_categorical_small_categories_filtered():
    """Categories below the 5% threshold are folded into longtail."""
    frequent = ['A'] * 10 + ['B'] * 8 + ['C'] * 4 + ['D'] * 3
    unique_vals = [f'unique_{i}' for i in range(75)]
    df = pl.DataFrame({'cat_col': frequent + unique_vals})
    cat_hist = _paf_cat_hist(df)
    # C and D are < 5% and must not appear as standalone categories.
    assert cat_hist.get('C', 0) == 0
    assert cat_hist.get('D', 0) == 0
