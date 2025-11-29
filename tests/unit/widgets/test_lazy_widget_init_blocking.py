import time
import polars as pl

from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor


class SlowPAFColumnExecutor(PAFColumnExecutor):
    def execute(self, ldf, execution_args):
        # Simulate expensive per-column computation (child process work).
        # This makes each column group take noticeable time even in mp.
        time.sleep(1.0)
        return super().execute(ldf, execution_args)


def _wide_df(num_cols: int, num_rows: int) -> pl.DataFrame:
    data = {f"c{i}": list(range(num_rows)) for i in range(num_cols)}
    return pl.DataFrame(data)


def test_lazy_widget_init_should_not_block_but_does_with_mp_and_slow_exec():
    """
    Expectation: LazyInfinitePolarsBuckarooWidget should display schema/empty data immediately
    and compute stats in the background. Reality: widget __init__ calls auto_compute_summary,
    which synchronously runs the executor (even when using MultiprocessingExecutor), blocking
    construction until the computation completes or times out.

    This test constructs a 51-column frame (forcing parallel path) and injects a SlowPAFColumnExecutor
    that sleeps in execute(). We assert widget construction returns quickly (< 0.3s). It currently
    fails because __init__ waits for the executor.run() to finish.
    """
    df = _wide_df(num_cols=51, num_rows=2)  # forces parallel path by column threshold
    ldf = df.lazy()

    t0 = time.time()
    # This call is expected to be non-blocking in the ideal design, but currently blocks.
    LazyInfinitePolarsBuckarooWidget(
        ldf,
        analysis_klasses=[],  # we only care about executor plumbing
        debug=True,
        column_executor_class=SlowPAFColumnExecutor,
    )
    elapsed = time.time() - t0

    # We want this to be fast if computations are backgrounded; set a tight bound that will fail now.
    assert elapsed < 0.3, f"Widget init blocked for {elapsed:.2f}s; should compute stats in background"
    #FIXME: this took 53 seconds, it's a really simple DF.  something with the column analytics is broken
    

