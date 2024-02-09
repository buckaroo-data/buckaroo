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




