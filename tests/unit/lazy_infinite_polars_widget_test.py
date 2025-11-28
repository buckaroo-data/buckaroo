import polars as pl

from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
from buckaroo.file_cache.base import FileCache
from pathlib import Path
import pytest
import time
from buckaroo.file_cache.base import Executor as _Exec


def _capture_sends(widget):
    sent = []
    def _send(payload, buffers):
        sent.append((payload, buffers))
    widget.send = _send  # type: ignore[attr-defined]
    return sent


def test_lazy_infinite_widget_init_and_summary():
    df = pl.DataFrame({'normal_int_series': [1, 2, 3, 4]})
    ldf = df.lazy()
    # Use slow executor to make the background transition observable
    from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
    import time as _time
    class SlowPAFColumnExecutor(PAFColumnExecutor):
        def execute(self, ldf, execution_args):
            _time.sleep(0.2)
            return super().execute(ldf, execution_args)

    w = LazyInfinitePolarsBuckarooWidget(ldf, column_executor_class=SlowPAFColumnExecutor)

    # df_meta should reflect lazy row and column counts
    assert w.df_meta['columns'] == 1
    assert w.df_meta['total_rows'] == 4

    # Synchronous path: populated immediately
    assert w.df_data_dict['all_stats'] != []

    # All stats should include orig/rewritten indicators after populated
    all_stats = w.df_data_dict['all_stats']
    idx_keys = [row['index'] for row in all_stats]
    assert 'orig_col_name' in idx_keys
    assert 'rewritten_col_name' in idx_keys

    # df_display_args wired for infinite viewer
    assert 'main' in w.df_display_args
    main_args = w.df_display_args['main']
    assert main_args['data_key'] == 'main'
    assert main_args['summary_stats_key'] == 'all_stats'
    assert 'df_viewer_config' in main_args
    assert 'column_config' in main_args['df_viewer_config']


def test_payload_slice_returns_requested_rows():
    df = pl.DataFrame({'a': [10, 20, 30, 40, 50]})
    ldf = df.lazy()
    w = LazyInfinitePolarsBuckarooWidget(ldf)
    captured = _capture_sends(w)

    # Request middle slice [1,4) => 3 rows
    w._handle_payload_args({'start': 1, 'end': 4})
    assert len(captured) == 1
    payload, buffers = captured[0]
    assert payload['type'] == 'infinite_resp'
    assert isinstance(buffers, list) and len(buffers) == 1

    # Decode parquet and verify row count equals requested slice length
    out_df = pl.read_parquet(buffers[0])
    # rewritten columns include 'index' and 'a'
    assert set(out_df.columns) >= set(['index', 'a'])
    assert out_df.shape[0] == 3
    assert out_df['a'].to_list() == [20, 30, 40]


def test_payload_sort_and_slice():
    df = pl.DataFrame({'x': [3, 1, 2, 5, 4]})
    ldf = df.lazy()
    w = LazyInfinitePolarsBuckarooWidget(ldf)
    captured = _capture_sends(w)

    # Determine rewritten name for 'x' (likely 'a')
    # Infer from df_display_args column_config
    cc = w.df_display_args['main']['df_viewer_config']['column_config']
    # pick the first non-index rewritten col
    rw = next(c['col_name'] for c in cc if c['col_name'] != 'index')

    # Request sorted ascending, first two rows
    w._handle_payload_args({'start': 0, 'end': 2, 'sort': rw, 'sort_direction': 'asc'})
    assert len(captured) == 1
    payload, buffers = captured[0]
    out_df = pl.read_parquet(buffers[0])
    # The smallest two values should be returned
    vals = out_df[rw].to_list()
    assert vals == sorted(vals)[:2]


def test_multiple_payloads_large_df():
    # 2000 rows
    df = pl.DataFrame({'v': list(range(2000))})
    ldf = df.lazy()
    w = LazyInfinitePolarsBuckarooWidget(ldf)
    captured = _capture_sends(w)

    # First window [0, 100)
    w._handle_payload_args({'start': 0, 'end': 100})
    # Second window [100, 250)
    w._handle_payload_args({'start': 100, 'end': 250})
    # Third window with a chained second_request
    w._handle_payload_args({'start': 500, 'end': 520, 'second_request': {'start': 900, 'end': 905}})

    # Expect three payloads; the third produces two sends (primary + second_request)
    assert len(captured) == 4

    # Validate first slice contents/size
    payload1, buffers1 = captured[0]
    out1 = pl.read_parquet(buffers1[0])
    assert out1.shape[0] == 100
    # rewritten col name for 'v' can be inferred from columns (exclude 'index')
    rw_cols1 = [c for c in out1.columns if c != 'index']
    assert len(rw_cols1) == 1
    rw1 = rw_cols1[0]
    assert out1[rw1].to_list()[0] == 0
    assert out1[rw1].to_list()[-1] == 99

    # Validate second slice contents/size
    payload2, buffers2 = captured[1]
    out2 = pl.read_parquet(buffers2[0])
    assert out2.shape[0] == 150
    rw_cols2 = [c for c in out2.columns if c != 'index']
    assert len(rw_cols2) == 1
    rw2 = rw_cols2[0]
    assert out2[rw2].to_list()[0] == 100
    assert out2[rw2].to_list()[-1] == 249

    # Validate third (primary) slice contents/size
    payload3a, buffers3a = captured[2]
    out3a = pl.read_parquet(buffers3a[0])
    assert out3a.shape[0] == 20
    rw_cols3a = [c for c in out3a.columns if c != 'index']
    rw3a = rw_cols3a[0]
    assert out3a[rw3a].to_list()[0] == 500
    assert out3a[rw3a].to_list()[-1] == 519

    # Validate third (second_request) slice contents/size
    payload3b, buffers3b = captured[3]
    out3b = pl.read_parquet(buffers3b[0])
    assert out3b.shape[0] == 5
    rw_cols3b = [c for c in out3b.columns if c != 'index']
    rw3b = rw_cols3b[0]
    assert out3b[rw3b].to_list() == [900, 901, 902, 903, 904]


def test_handle_payload_never_collects_base(monkeypatch):
    """
    Guard that _handle_payload_args never calls collect() on the original LazyFrame,
    only on sliced frames.
    """
    df = pl.DataFrame({'v': list(range(200))})
    ldf = df.lazy()
    w = LazyInfinitePolarsBuckarooWidget(ldf)
    captured = _capture_sends(w)

    base_ldf = w._ldf
    orig_collect = pl.LazyFrame.collect

    def guarded_collect(self, *args, **kwargs):
        if self is base_ldf:
            raise AssertionError("Full collect on base LazyFrame was called")
        return orig_collect(self, *args, **kwargs)

    # Patch after widget init to avoid blocking summary computation
    monkeypatch.setattr(pl.LazyFrame, "collect", guarded_collect, raising=True)

    # Now call payload handler; it must collect only the sliced frame
    w._handle_payload_args({'start': 10, 'end': 20})
    assert len(captured) == 1
    payload, buffers = captured[0]
    out_df = pl.read_parquet(buffers[0])
    assert out_df.shape[0] == 10


def test_synchronous_populates_immediately():
    df = pl.DataFrame({'v': [1, 2, 3]})
    ldf = df.lazy()
    # Make it slow to assert background behavior
    from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
    import time as _time
    class SlowPAFColumnExecutor(PAFColumnExecutor):
        def execute(self, ldf, execution_args):
            _time.sleep(0.2)
            return super().execute(ldf, execution_args)

    w = LazyInfinitePolarsBuckarooWidget(ldf, column_executor_class=SlowPAFColumnExecutor)
    assert w.df_data_dict['all_stats'] != []

def test_cache_short_circuit_populates_immediately(tmp_path):
    # Prepare a fake cached merged_sd
    cached_sd = {
        'a': {'orig_col_name': 'v', 'rewritten_col_name': 'a', 'mean': 2.0, 'null_count': 0}
    }
    fc = FileCache()
    fpath = tmp_path / "fake.parq"
    fpath.write_text("placeholder")
    fc.upsert_file_metadata(Path(fpath), {'merged_sd': cached_sd})

    df = pl.DataFrame({'v': [1, 2, 3]})
    ldf = df.lazy()
    # Use a failing sync executor to ensure we did not run compute if cache is present
    from buckaroo.file_cache.base import Executor as _Exec
    class FailingExec(_Exec):
        def run(self):  # type: ignore[override]
            raise RuntimeError("should not be called due to cache hit")

    w = LazyInfinitePolarsBuckarooWidget(ldf, file_path=str(fpath), file_cache=fc, sync_executor_class=FailingExec)
    assert w.df_data_dict['all_stats'] != []
    idx_keys = [row['index'] for row in w.df_data_dict['all_stats']]
    assert 'orig_col_name' in idx_keys and 'mean' in idx_keys

def test_executor_selection_thresholds_and_fallback():
    # 51 columns triggers parallel selection
    data = {f'c{i}': [i] for i in range(51)}
    df = pl.DataFrame(data)
    ldf = df.lazy()

    # Track which executor path was used

    class TrackingSync(_Exec):
        used = False
        def run(self):  # type: ignore[override]
            TrackingSync.used = True
            return super().run()
    class TrackingPar(_Exec):
        used = False
        def run(self):  # type: ignore[override]
            TrackingPar.used = True
            return super().run()

    w = LazyInfinitePolarsBuckarooWidget(ldf, sync_executor_class=TrackingSync, parallel_executor_class=TrackingPar)
    assert TrackingPar.used is True

    # Now test fallback: small df chooses sync, but sync fails, fallback to parallel
    small_df = pl.DataFrame({'x': [1, 2, 3]})
    small_ldf = small_df.lazy()
    class FailingSync(_Exec):
        def run(self):  # type: ignore[override]
            raise RuntimeError("fail sync")
    class WorkingPar(_Exec):
        used = False
        def run(self):  # type: ignore[override]
            WorkingPar.used = True
            return super().run()

    w2 = LazyInfinitePolarsBuckarooWidget(small_ldf, sync_executor_class=FailingSync, parallel_executor_class=WorkingPar)
    assert WorkingPar.used is True
    assert w2.df_data_dict['all_stats'] != []

def test_full_summary_present_immediately():
    df = pl.DataFrame({'c1': [1, 2, 3], 'c2': [10, 20, 30], 'c3': [7, 8, 9]})
    ldf = df.lazy()
    from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
    import time as _time
    class SlowPAFColumnExecutor(PAFColumnExecutor):
        def execute(self, ldf, execution_args):
            # small sleep per column-chunk to allow polling
            _time.sleep(0.15)
            return super().execute(ldf, execution_args)

    w = LazyInfinitePolarsBuckarooWidget(ldf, column_executor_class=SlowPAFColumnExecutor)
    rows = w.df_data_dict['all_stats']
    assert rows != []
    ocn_rows = [r for r in rows if r.get('index') == 'orig_col_name']
    assert ocn_rows
    row = ocn_rows[0]
    present_cols = [k for k in row.keys() if k not in ('index', 'level_0')]
    assert len(present_cols) == 3

