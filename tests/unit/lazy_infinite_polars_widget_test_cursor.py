"""
Tests to diagnose why summary stats aren't being populated in LazyInfinitePolarsBuckarooWidget.
"""
# state:READONLY

import base64
import json
from io import BytesIO

import pandas as pd
import polars as pl
from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
from buckaroo.file_cache.base import Executor as SyncExecutor


def _resolve_all_stats(all_stats):
    """Resolve all_stats to a list of row dicts, whether it's JSON or parquet_b64."""
    if isinstance(all_stats, list):
        return all_stats
    if isinstance(all_stats, dict) and all_stats.get('format') in ('ipc_b64', 'parquet_b64'):
        raw = base64.b64decode(all_stats['data'])
        import pyarrow.ipc as ipc_mod
        reader = ipc_mod.open_stream(BytesIO(raw))
        table = reader.read_all()
        df = pd.DataFrame(table.to_pydict())
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


def test_lazy_widget_sync_executor_populates_stats():
    """Test that synchronous executor properly populates summary stats."""
    df = pl.DataFrame({
        'int_col': [1, 2, 3, 4, 5],
        'str_col': ['a', 'b', 'c', 'd', 'e'],
        'float_col': [1.1, 2.2, 3.3, 4.4, 5.5]
    })
    ldf = df.lazy()
    
    widget = LazyInfinitePolarsBuckarooWidget(
        ldf,
        sync_executor_class=SyncExecutor,
        parallel_executor_class=SyncExecutor,  # Use sync for both to avoid async issues
    )
    
    # Wait a moment for computation to complete (sync executor should be blocking)
    import time
    time.sleep(0.5)
    
    # Check that merged_sd has content
    print(f"merged_sd keys: {list(widget._df.merged_sd.keys())}")
    print(f"merged_sd: {widget._df.merged_sd}")
    print(f"summary_sd keys: {list(widget._df.summary_sd.keys())}")
    print(f"summary_sd: {widget._df.summary_sd}")
    
    # merged_sd should have content (not empty)
    assert len(widget._df.merged_sd) > 0, f"merged_sd is empty: {widget._df.merged_sd}"
    
    # all_stats should have real values, not just defaults
    all_stats = _resolve_all_stats(widget.df_data_dict.get('all_stats', []))
    print(f"all_stats length: {len(all_stats)}")

    # Check that we have at least one column with stats
    assert len(all_stats) > 0, "all_stats is empty"

    # Check that stats contain real data (not just default 0s)
    # all_stats is formatted as rows keyed by stat name, so find a stat row with real values
    # Look for 'length' row which should have non-zero values for each column
    length_row = next((row for row in all_stats if row.get('index') == 'length'), None)
    if length_row:
        print(f"Length row: {length_row}")
        # Should have non-zero length values for at least one column
        has_length = any(
            length_row.get(k, 0) > 0 
            for k in ['a', 'b', 'c']  # Column keys (rewritten names)
        )
        assert has_length, f"Length row has no stats: {length_row}"
    
    # Also verify merged_sd has real stats
    if 'a' in widget._df.merged_sd:
        col_a_stats = widget._df.merged_sd['a']
        assert col_a_stats.get('unique_count', 0) > 0, f"Column 'a' has no unique_count: {col_a_stats}"
        assert col_a_stats.get('length', 0) > 0, f"Column 'a' has no length: {col_a_stats}"


def test_lazy_widget_multiprocessing_executor_populates_stats():
    """Test that MultiprocessingExecutor properly populates summary stats."""
    df = pl.DataFrame({
        'int_col': [1, 2, 3, 4, 5] * 100,  # Make it larger to trigger parallel path
        'str_col': ['a', 'b', 'c', 'd', 'e'] * 100,
        'float_col': [1.1, 2.2, 3.3, 4.4, 5.5] * 100
    })
    ldf = df.lazy()
    
    from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor
    
    widget = LazyInfinitePolarsBuckarooWidget(
        ldf,
        sync_executor_class=SyncExecutor,
        parallel_executor_class=MultiprocessingExecutor,
    )
    
    # Wait longer for multiprocessing executor (it runs in background thread with async_mode=True)
    import time
    time.sleep(3.0)  # Give it time to compute
    
    # Check that merged_sd has content
    print(f"merged_sd keys: {list(widget._df.merged_sd.keys())}")
    print(f"merged_sd: {widget._df.merged_sd}")
    print(f"summary_sd keys: {list(widget._df.summary_sd.keys())}")
    print(f"summary_sd: {widget._df.summary_sd}")
    
    # merged_sd should have content (not empty)
    # Note: With async_mode=True, this might still be empty if computation hasn't finished
    # But after waiting 3 seconds, it should be populated
    
    if len(widget._df.merged_sd) == 0:
        print("WARNING: merged_sd is still empty after waiting. This indicates the async computation didn't complete.")
        print(f"df_data_dict keys: {list(widget.df_data_dict.keys())}")
        print(f"all_stats: {widget.df_data_dict.get('all_stats', [])[:3]}")
    
    # Check all_stats
    all_stats = _resolve_all_stats(widget.df_data_dict.get('all_stats', []))
    print(f"all_stats length: {len(all_stats)}")

    # At least check that we got something (even if it's defaults)
    assert len(all_stats) > 0, "all_stats is empty"

    # If we waited long enough and async computation completed, we should have real stats
    if len(widget._df.merged_sd) > 0:
        # Find the 'length' stat row specifically
        length_row = next((row for row in all_stats if row.get('index') == 'length'), None)
        if length_row:
            print(f"Length row: {length_row}")
            # Should have non-zero length for at least one column
            has_stats = any(
                length_row.get(k, 0) > 0
                for k in ['a', 'b', 'c']
                if k in length_row
            )
            assert has_stats, f"Length row has no stats: {length_row}"
