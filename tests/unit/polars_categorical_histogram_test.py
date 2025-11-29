"""
Tests to diagnose differences in categorical histogram computation
between the full Polars pipeline and the PAF/ColumnExecutor path.

These tests compare categorical_histogram results from both paths
to identify which side is correct and what the differences are.
"""
import polars as pl
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PlTyping, BasicAnalysis, HistogramAnalysis,
    ComputedDefaultSummaryStats)
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysisPipeline)
from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
from buckaroo.file_cache.base import FileCache

HA_CLASSES = [VCAnalysis, PlTyping, BasicAnalysis, ComputedDefaultSummaryStats, HistogramAnalysis]


def test_simple_categorical_two_values():
    """Simple test: two categories, equal frequency"""
    df = pl.DataFrame({'cat_col': ['A', 'B'] * 50})  # 100 rows, 50 each
    
    # Full pipeline
    full_summary, full_errs = PolarsAnalysisPipeline.full_produce_summary_df(
        df, HA_CLASSES, debug=False
    )
    
    # PAF path
    ldf = df.lazy()
    ced = ColumnExecutorDataflow(ldf, analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    paf_summary = ced.merged_sd
    
    print("\n=== Simple Two Values Test ===")
    print(f"Full pipeline summary keys: {list(full_summary.keys())}")
    print(f"PAF path summary keys: {list(paf_summary.keys())}")
    
    # Find the column that corresponds to 'cat_col'
    full_cat_key = None
    for key, meta in full_summary.items():
        if meta.get('orig_col_name') == 'cat_col':
            full_cat_key = key
            break
    if full_cat_key is None:
        # Try first key
        full_cat_key = list(full_summary.keys())[0] if full_summary else None
    
    paf_cat_key = None
    for key, meta in paf_summary.items():
        if meta.get('orig_col_name') == 'cat_col':
            paf_cat_key = key
            break
    if paf_cat_key is None:
        # Try first key
        paf_cat_key = list(paf_summary.keys())[0] if paf_summary else None
    
    print(f"Full pipeline cat_col key: {full_cat_key}")
    print(f"PAF path cat_col key: {paf_cat_key}")
    
    if full_cat_key:
        full_cat_hist = full_summary[full_cat_key].get('categorical_histogram', {})
        print(f"Full pipeline categorical_histogram: {full_cat_hist}")
    else:
        full_cat_hist = {}
        print("Full pipeline: no cat_col found")
    
    if paf_cat_key:
        paf_cat_hist = paf_summary[paf_cat_key].get('categorical_histogram', {})
        paf_vc = paf_summary[paf_cat_key].get('value_counts')
        print(f"PAF path categorical_histogram: {paf_cat_hist}")
        print(f"PAF path value_counts type: {type(paf_vc)}")
        if paf_vc is not None and hasattr(paf_vc, 'name'):
            print(f"PAF path value_counts name: '{paf_vc.name}'")
    else:
        paf_cat_hist = {}
        print("PAF path: no cat_col found")
    
    print(f"Match: {full_cat_hist == paf_cat_hist}")
    
    # Both should have A: 0.5, B: 0.5, longtail: 0.0, unique: 0.0
    # Don't assert yet, just report
    if full_cat_hist != paf_cat_hist:
        print(f"DIAGNOSIS: Mismatch detected - full={full_cat_hist}, paf={paf_cat_hist}")


def test_simple_categorical_three_values():
    """Simple test: three categories, different frequencies"""
    df = pl.DataFrame({'cat_col': ['A'] * 50 + ['B'] * 30 + ['C'] * 20})  # 100 rows
    
    # Full pipeline
    full_summary, full_errs = PolarsAnalysisPipeline.full_produce_summary_df(
        df, HA_CLASSES, debug=False
    )
    full_cat_hist = full_summary.get('a', {}).get('categorical_histogram', {})
    
    # PAF path
    ldf = df.lazy()
    ced = ColumnExecutorDataflow(ldf, analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    paf_summary = ced.merged_sd
    paf_cat_hist = paf_summary.get('a', {}).get('categorical_histogram', {})
    
    print("\n=== Simple Three Values Test ===")
    print(f"Full pipeline categorical_histogram: {full_cat_hist}")
    print(f"PAF path categorical_histogram: {paf_cat_hist}")
    print(f"Match: {full_cat_hist == paf_cat_hist}")
    
    # Expected: A: 0.5, B: 0.3, C: 0.2, longtail: 0.0, unique: 0.0
    assert full_cat_hist == paf_cat_hist, f"Mismatch: full={full_cat_hist}, paf={paf_cat_hist}"


def test_categorical_with_longtail():
    """Test with many unique values that should create a longtail"""
    # 7 frequent values + many unique values
    frequent = ['A'] * 30 + ['B'] * 20 + ['C'] * 15 + ['D'] * 10 + ['E'] * 8 + ['F'] * 7 + ['G'] * 6
    unique_vals = [f'unique_{i}' for i in range(4)]  # 4 unique values, 1 count each
    df = pl.DataFrame({'cat_col': frequent + unique_vals})  # 100 rows total
    
    # Full pipeline
    full_summary, full_errs = PolarsAnalysisPipeline.full_produce_summary_df(
        df, HA_CLASSES, debug=False
    )
    full_cat_hist = full_summary.get('a', {}).get('categorical_histogram', {})
    
    # PAF path
    ldf = df.lazy()
    ced = ColumnExecutorDataflow(ldf, analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    paf_summary = ced.merged_sd
    paf_cat_hist = paf_summary.get('a', {}).get('categorical_histogram', {})
    
    print("\n=== Longtail Test ===")
    print(f"Full pipeline categorical_histogram: {full_cat_hist}")
    print(f"PAF path categorical_histogram: {paf_cat_hist}")
    print(f"Match: {full_cat_hist == paf_cat_hist}")
    
    # Check that both have longtail and unique
    assert 'longtail' in full_cat_hist, "Full pipeline should have longtail"
    assert 'unique' in full_cat_hist, "Full pipeline should have unique"
    assert 'longtail' in paf_cat_hist, "PAF path should have longtail"
    assert 'unique' in paf_cat_hist, "PAF path should have unique"
    
    # Compare values (allowing small floating point differences)
    for key in set(list(full_cat_hist.keys()) + list(paf_cat_hist.keys())):
        if key in ['longtail', 'unique']:
            full_val = full_cat_hist.get(key, 0)
            paf_val = paf_cat_hist.get(key, 0)
            assert abs(full_val - paf_val) < 0.01, f"Mismatch for {key}: full={full_val}, paf={paf_val}"


def test_categorical_from_test_histogram_analysis():
    """Use the exact data from test_histogram_analysis to compare"""
    cats = [chr(x) for x in range(97, 102)] * 2  # a, b, c, d, e each twice = 10
    cats += [chr(x) for x in range(103, 113)]    # f, g, h, i, j each once = 10
    cats += ['foo'] * 30 + ['bar'] * 50         # 80 more
    # Total: 100 rows
    
    df = pl.DataFrame({'categories': cats})
    
    # Full pipeline
    full_summary, full_errs = PolarsAnalysisPipeline.full_produce_summary_df(
        df, HA_CLASSES, debug=False
    )
    full_cat_hist = full_summary.get('a', {}).get('categorical_histogram', {})
    
    # PAF path
    ldf = df.lazy()
    ced = ColumnExecutorDataflow(ldf, analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    paf_summary = ced.merged_sd
    paf_cat_hist = paf_summary.get('a', {}).get('categorical_histogram', {})
    
    print("\n=== Test Histogram Analysis Data ===")
    print(f"Full pipeline categorical_histogram: {full_cat_hist}")
    print(f"PAF path categorical_histogram: {paf_cat_hist}")
    print(f"Match: {full_cat_hist == paf_cat_hist}")
    
    # Expected from test_histogram_analysis: {'bar': 0.5, 'foo': 0.3, 'longtail': 0.1, 'unique': 0.1}
    expected = {'bar': 0.5, 'foo': 0.3, 'longtail': 0.1, 'unique': 0.1}
    
    print(f"Expected: {expected}")
    print(f"Full matches expected: {full_cat_hist == expected}")
    print(f"PAF matches expected: {paf_cat_hist == expected}")
    
    # Compare key by key
    for key in set(list(full_cat_hist.keys()) + list(paf_cat_hist.keys()) + list(expected.keys())):
        full_val = full_cat_hist.get(key, None)
        paf_val = paf_cat_hist.get(key, None)
        exp_val = expected.get(key, None)
        print(f"  {key}: full={full_val}, paf={paf_val}, expected={exp_val}")


def test_categorical_small_categories_filtered():
    """Test that categories below 5% threshold are filtered into longtail"""
    # Create data where some categories are < 5% and should be filtered
    # 100 rows: A=10 (10%), B=8 (8%), C=4 (4% - should be filtered), D=3 (3% - filtered), rest unique
    frequent = ['A'] * 10 + ['B'] * 8 + ['C'] * 4 + ['D'] * 3
    unique_vals = [f'unique_{i}' for i in range(75)]  # 75 unique values
    df = pl.DataFrame({'cat_col': frequent + unique_vals})  # 100 rows total
    
    # Full pipeline
    full_summary, full_errs = PolarsAnalysisPipeline.full_produce_summary_df(
        df, HA_CLASSES, debug=False
    )
    full_cat_hist = full_summary.get('a', {}).get('categorical_histogram', {})
    
    # PAF path
    ldf = df.lazy()
    ced = ColumnExecutorDataflow(ldf, analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    paf_summary = ced.merged_sd
    paf_cat_hist = paf_summary.get('a', {}).get('categorical_histogram', {})
    
    print("\n=== Small Categories Filtered Test ===")
    print(f"Full pipeline categorical_histogram: {full_cat_hist}")
    print(f"PAF path categorical_histogram: {paf_cat_hist}")
    print(f"Match: {full_cat_hist == paf_cat_hist}")
    
    # C and D should be in longtail (both < 5%), not as separate categories
    assert 'C' not in full_cat_hist or full_cat_hist.get('C', 0) == 0, "C should be filtered to longtail"
    assert 'D' not in full_cat_hist or full_cat_hist.get('D', 0) == 0, "D should be filtered to longtail"


def test_categorical_value_counts_structure():
    """Test to see what value_counts structure looks like in both paths"""
    df = pl.DataFrame({'cat_col': ['A', 'B', 'C'] * 10})  # 30 rows
    
    # Full pipeline
    full_summary, full_errs = PolarsAnalysisPipeline.full_produce_summary_df(
        df, HA_CLASSES, debug=False
    )
    full_vc = full_summary.get('a', {}).get('value_counts')
    
    # PAF path
    ldf = df.lazy()
    ced = ColumnExecutorDataflow(ldf, analysis_klasses=HA_CLASSES)
    ced.compute_summary_with_executor(file_cache=FileCache())
    paf_summary = ced.merged_sd
    paf_vc = paf_summary.get('a', {}).get('value_counts')
    
    print("\n=== Value Counts Structure Test ===")
    print(f"Full pipeline value_counts type: {type(full_vc)}")
    if hasattr(full_vc, 'name'):
        print(f"Full pipeline value_counts name: '{full_vc.name}'")
    if hasattr(full_vc, 'explode'):
        try:
            full_vc_exploded = full_vc.explode()
            print(f"Full pipeline value_counts length: {len(full_vc_exploded)}")
            if len(full_vc_exploded) > 0:
                print(f"Full pipeline value_counts first 3: {full_vc_exploded[:3]}")
        except Exception as e:
            print(f"Full pipeline value_counts explode error: {e}")
    
    print(f"PAF path value_counts type: {type(paf_vc)}")
    if hasattr(paf_vc, 'name'):
        print(f"PAF path value_counts name: '{paf_vc.name}'")
    if hasattr(paf_vc, 'explode'):
        try:
            paf_vc_exploded = paf_vc.explode()
            print(f"PAF path value_counts length: {len(paf_vc_exploded)}")
            if len(paf_vc_exploded) > 0:
                print(f"PAF path value_counts first 3: {paf_vc_exploded[:3]}")
        except Exception as e:
            print(f"PAF path value_counts explode error: {e}")
    
    # Check if they're the same
    if hasattr(full_vc, 'explode') and hasattr(paf_vc, 'explode'):
        try:
            full_exploded = full_vc.explode()
            paf_exploded = paf_vc.explode()
            print(f"Value counts match: {len(full_exploded) == len(paf_exploded)}")
            if len(full_exploded) == len(paf_exploded) and len(full_exploded) > 0:
                # Compare first few
                for i in range(min(3, len(full_exploded))):
                    print(f"  [{i}] full={full_exploded[i]}, paf={paf_exploded[i]}, match={full_exploded[i] == paf_exploded[i]}")
        except Exception as e:
            print(f"Comparison error: {e}")
