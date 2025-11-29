"""
Test to understand why full pipeline doesn't fail on mean() for strings
but PAF path does.
"""
import polars as pl
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PlTyping, BasicAnalysis, HistogramAnalysis,
    ComputedDefaultSummaryStats)
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    polars_produce_series_df)
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor

HA_CLASSES = [VCAnalysis, PlTyping, BasicAnalysis, ComputedDefaultSummaryStats, HistogramAnalysis]


def test_full_pipeline_error_handling():
    """Test how full pipeline handles mean() on string columns"""
    df = pl.DataFrame({'cat_col': ['A', 'B'] * 50})
    
    print("\n=== Full Pipeline Error Handling ===")
    
    # This is what full pipeline does internally
    series_stats, errs = polars_produce_series_df(df, HA_CLASSES, debug=True)
    
    print(f"Series stats keys: {list(series_stats.keys())}")
    print(f"Errors: {errs}")
    
    # Check if errors were caught
    if errs:
        print(f"Full pipeline caught {len(errs)} errors but continued")
        for key, (error, klass) in errs.items():
            print(f"  Error in {key}: {type(error).__name__}: {error}")
    else:
        print("Full pipeline: No errors recorded")
    
    # Check what stats were computed
    for key, stats in series_stats.items():
        print(f"\nColumn '{key}' stats:")
        print(f"  Keys: {list(stats.keys())}")
        if 'value_counts' in stats:
            vc = stats['value_counts']
            if hasattr(vc, 'explode'):
                try:
                    vc_exploded = vc.explode()
                    print(f"  value_counts length: {len(vc_exploded)}")
                except Exception:
                    pass


def test_paf_executor_error_handling():
    """Test how PAF executor handles mean() on string columns"""
    df = pl.DataFrame({'cat_col': ['A', 'B'] * 50})
    ldf = df.lazy()
    
    print("\n=== PAF Executor Error Handling ===")
    
    executor = PAFColumnExecutor(HA_CLASSES)
    existing_stats = {'cat_col': {'__missing_hash__': False}}
    exec_args = executor.get_execution_args(existing_stats)
    
    print(f"Expressions to execute: {len(exec_args.expressions)}")
    print(f"Columns: {exec_args.columns}")
    
    # Try to execute
    try:
        results = executor.execute(ldf, exec_args)
        print("PAF executor: SUCCESS")
        print(f"Results keys: {list(results.keys()) if results else 'None'}")
    except Exception as e:
        print("PAF executor: FAILED")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {e}")
        print("  DIAGNOSIS: PAF executor does NOT catch errors - execution fails completely")


def test_expression_execution_directly():
    """Test executing expressions directly to see error behavior"""
    df = pl.DataFrame({'cat_col': ['A', 'B'] * 50})
    ldf = df.lazy()
    
    print("\n=== Direct Expression Execution ===")
    
    from buckaroo.pluggable_analysis_framework.polars_analysis_management import polars_select_expressions
    
    # Get all expressions
    all_expressions = polars_select_expressions(HA_CLASSES)
    print(f"Total expressions: {len(all_expressions)}")
    
    # Try executing all at once (like full pipeline does)
    print("\n--- Executing all expressions together ---")
    try:
        result_all = ldf.select(*all_expressions).collect()
        print("SUCCESS: All expressions executed together")
        print(f"Result columns: {result_all.columns[:5]}...")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        print("  DIAGNOSIS: Full pipeline must handle this differently")
    
    # Try executing with error handling (like full pipeline might)
    print("\n--- Executing with try/except per expression ---")
    successful = []
    failed = []
    for expr in all_expressions:
        try:
            ldf.select(expr).collect()
            successful.append(expr)
        except Exception as e:
            failed.append((expr, e))
    
    print(f"Successful expressions: {len(successful)}")
    print(f"Failed expressions: {len(failed)}")
    if failed:
        print("  Failed examples:")
        for expr, error in failed[:3]:
            print(f"    {type(error).__name__}: {error}")


def test_full_pipeline_vs_paf_expressions():
    """Compare what expressions full pipeline uses vs PAF executor"""
    print("\n=== Expression Comparison ===")
    
    # Full pipeline expressions
    from buckaroo.pluggable_analysis_framework.polars_analysis_management import polars_select_expressions
    full_expressions = polars_select_expressions(HA_CLASSES)
    print(f"Full pipeline expressions count: {len(full_expressions)}")
    
    # PAF executor expressions
    executor = PAFColumnExecutor(HA_CLASSES)
    existing_stats = {'cat_col': {'__missing_hash__': False}}
    paf_exec_args = executor.get_execution_args(existing_stats)
    paf_expressions = paf_exec_args.expressions
    print(f"PAF executor expressions count: {len(paf_expressions)}")
    
    # Compare
    print(f"\nExpression difference: {len(paf_expressions) - len(full_expressions)}")
    
    # Check if PAF has expressions that full pipeline doesn't
    full_expr_strs = [str(e) for e in full_expressions]
    #paf_expr_strs = [str(e) for e in paf_expressions]
    
    paf_only = [e for e in paf_expressions if str(e) not in full_expr_strs]
    print(f"PAF-only expressions: {len(paf_only)}")
    if paf_only:
        print("  Examples:")
        for e in paf_only[:3]:
            print(f"    {e}")
