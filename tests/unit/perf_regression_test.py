import pandas as pd
import numpy as np
import buckaroo
import time

def float_df(N_rows, K_columns):
    return pd.DataFrame(
        {chr(i+97): np.random.random_sample(N_rows) for i in range(K_columns)})


"""
The idea of this is to make a relative timing comparison between just insantiating a dataframe and the full buckaroo testing.  it's crude but should alert to major performance regressions.  particularly with json serialization

"""
# %timeit float_df(100_000,20) 9ms on my laptop

def bw_do_stuff(df, **kwargs):
    buckaroo.buckaroo_widget.BuckarooWidget(df, **kwargs)

#%timeit bw_do_stuff(float_df(100_000, 20)) 500 ms on my laptop


# the slow part is serialization to json, not summary stats
# %timeit bw_do_stuff2(float_df(10_000, 5)) 140 ms on my laptop
# %timeit bw_do_stuff2(float_df(100_000, 5)) 150ms on my laptop


def test_basic_instantiation():
    t_start = time.time()
    float_df(100_000, 20)
    t_end = time.time()

    np_time = t_end - t_start
    assert np_time < 10

    bw_start = time.time()
    bw_do_stuff(float_df(10_000,5))
    bw_end = time.time()
    bw_time_1 = bw_end - bw_start
    
    assert bw_time_1 < np_time * 50


    bw_start2 = time.time()
    bw_do_stuff(float_df(100_000,5))
    bw_end2 = time.time()
    bw_time_2 = bw_end2 - bw_start2

    assert bw_time_2 < np_time * 60


# ============================================================
# Issue #706 — pandas widget construction must not perform full DataFrame
# equality during traitlets change-detection. Cost is O(rows × cols) and
# dominated 78% of construction time on a real 883k×26 CSV.
# ============================================================

def _best_of(fn, n=3):
    fn()  # warmup
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def test_pandas_infinite_widget_no_full_dataframe_eq():
    """Regression for #706: traitlets _compare must use identity for DF traits.

    Construction time on a 200k×10 object-dtype frame must not scale anywhere
    near linearly with cells (the bug makes it scale exactly linearly).
    """
    from buckaroo.buckaroo_widget import BuckarooInfiniteWidget

    big = pd.DataFrame({f'c{i}': ['xyz'] * 200_000 for i in range(10)})
    small = pd.DataFrame({f'c{i}': ['xyz'] * 1_000 for i in range(10)})

    # Warmup imports + first-DAG-build so the first measured call doesn't pay
    # cold-start cost.
    BuckarooInfiniteWidget(small)
    BuckarooInfiniteWidget(big)

    big_t = _best_of(lambda: BuckarooInfiniteWidget(big), n=3)
    small_t = _best_of(lambda: BuckarooInfiniteWidget(small), n=3)
    ratio = big_t / max(small_t, 1e-6)

    # Bug today: ratio ~6-8x (DataFrame.__eq__ scales with cells).
    # Fixed: ratio ~1.5-2x (just stat-pipeline overhead on more rows).
    # 3.5x leaves CI headroom and still discriminates clearly.
    assert ratio < 3.5, (
        f"BuckarooInfiniteWidget on 200k×10 obj df is {big_t*1000:.0f}ms, "
        f"{ratio:.1f}x the 1k×10 baseline ({small_t*1000:.0f}ms). "
        "Construction is scaling with cells — likely traitlets DataFrame.__eq__ "
        "regression (#706)."
    )
