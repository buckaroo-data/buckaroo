import pandas as pd
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2
from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2

# histogram (@stat) depends on typing_stats (is_numeric) and the summary-stat
# functions, so the DAG needs the full PD_ANALYSIS_V2 set wired together.
HISTO_KLASSES = list(PD_ANALYSIS_V2)

# table-format
INT_ARR = [33, 41, 11, 46, 42, 44, 31, 25, 16, 24, 26,  7, 19, 23, 20, 46, 10,  4, 31, 45, 40, 37, 48, 21, 19, 20, 19,
           14, 14, 26, 36, 24, 21, 41, 19, 17, 24, 27, 32, 30, 19, 49, 22, 20, 16,  7, 45, 10, 23, 44, 28, 44, 15, 29,
           34,  3, 44, 19, 20, 27,  1, 35, 34, 42, 12,  9, 21, 32, 40, 41, 49, 47, 16, 25, 20, 11, 28, 13, 30,  6, 34,
           16, 37, 21,  7, 34, 34, 29, 24,  2,  7, 17, 13, 22, 13, 32, 11, 24, 24, 31, 11,  9, 39, 40, 36, 20, 46, 31,
           37, 27, 25,  9, 27, 41, 13, 35, 33, 24,  8, 25, 12, 28, 26, 17,  7, 18, 12,  6, 45, 42, 32, 38, 31, 25, 33,
           13, 24, 23, 40, 18, 33, 42,  7, 40, 48, 29, 27, 13, 38, 35, 33, 24, 40, 19, 47, 38,  8,  3,  6, 48,  9, 17,
           13, 46,  6,  3, 34, 43,  6,  9, 28,  4, 49, 10, 14, 36, 48, 39,  1, 37, 41, 37, 43, 43,  6, 23,  6, 30, 27,
           11, 19, 19, 34, 14, 37, 42, 15,  6, 48, 32]

test_df = pd.DataFrame({'a': INT_ARR})

def _assert_ha(ha):
    assert ha['low_tail'] == 1.99
    assert ha['high_tail'] == 49.0

    assert ha['normalized_populations'] == [
        0.07179487179487179, 0.1076923076923077, 0.08205128205128205, 0.1282051282051282,
        0.09743589743589744, 0.1076923076923077, 0.1282051282051282, 0.07692307692307693,
        0.1076923076923077, 0.09230769230769231]
    #numpy arrays need special comparison that I will look at later


def _process(df, klasses=HISTO_KLASSES):
    return StatPipeline(klasses, unit_test=False).process_df(df, debug=True)


def test_histogram_args():
    """The Histogram analysis produces the expected histogram_args."""
    sdf, errs = _process(test_df)
    _assert_ha(sdf['a']['histogram_args'])


def test_no_meat():
    """Nearly-constant column with outliers must not error.
    Nearly-constant column with outliers fails to display #264
    https://github.com/paddymul/buckaroo/issues/264
    """
    df = pd.DataFrame({'no_meat': [1] * 400 + [10, 20, 30, 40, 50]})
    sdf, errs = _process(df)
    assert errs == []


def test_non_nunique_index():
    """histograms can fail with non-unique indexes.  non-unique indexes frequently occur as the result of concatting dataframes.  This should not fail
    """
    df = pd.DataFrame({'bad': pd.Series([1,2, pd.NA,  1],
        index= [11000, 11001, 11002,  11000]).astype('Int64')})
    sdf, errs = _process(df)
    assert errs == []


def test_dfstats_histogram():
    stats = DfStatsV2(test_df, HISTO_KLASSES, 'test_df', debug=True)
    _assert_ha(stats.sdf['a']['histogram_args'])
