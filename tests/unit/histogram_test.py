import pandas as pd
from buckaroo.pluggable_analysis_framework.analysis_management import (
    DfStats, produce_series_df, AnalysisPipeline)
from buckaroo.customizations.histogram import Histogram
from buckaroo.customizations.analysis import (
    TypingStats, ComputedDefaultSummaryStats, DefaultSummaryStats)

INT_ARR = [33, 41, 11, 46, 42, 44, 31, 25, 16, 24, 26,  7, 19, 23, 20, 46, 10,
 4, 31, 45, 40, 37, 48, 21, 19, 20, 19, 14, 14, 26, 36, 24, 21, 41,
 19, 17, 24, 27, 32, 30, 19, 49, 22, 20, 16,  7, 45, 10, 23, 44, 28,
 44, 15, 29, 34,  3, 44, 19, 20, 27,  1, 35, 34, 42, 12,  9, 21, 32,
 40, 41, 49, 47, 16, 25, 20, 11, 28, 13, 30,  6, 34, 16, 37, 21,  7,
 34, 34, 29, 24,  2,  7, 17, 13, 22, 13, 32, 11, 24, 24, 31, 11,  9,
 39, 40, 36, 20, 46, 31, 37, 27, 25,  9, 27, 41, 13, 35, 33, 24,  8,
 25, 12, 28, 26, 17,  7, 18, 12,  6, 45, 42, 32, 38, 31, 25, 33, 13,
 24, 23, 40, 18, 33, 42,  7, 40, 48, 29, 27, 13, 38, 35, 33, 24, 40,
 19, 47, 38,  8,  3,  6, 48,  9, 17, 13, 46,  6,  3, 34, 43,  6,  9,
 28,  4, 49, 10, 14, 36, 48, 39,  1, 37, 41, 37, 43, 43,  6, 23,  6,
 30, 27, 11, 19, 19, 34, 14, 37, 42, 15,  6, 48, 32]

test_df = pd.DataFrame({'a': INT_ARR})

def _assert_ha(ha):
    assert ha['low_tail'] == 1.99
    assert ha['high_tail'] == 49.0

    assert ha['normalized_populations'] == [
        0.07179487179487179, 0.1076923076923077, 0.08205128205128205, 0.1282051282051282,
        0.09743589743589744, 0.1076923076923077, 0.1282051282051282, 0.07692307692307693,
        0.1076923076923077, 0.09230769230769231]
    #numpy arrays need special comparison that I will look at later
    
    # assert ha['meat_histogram'] == (
    #             np.array([14, 21, 16, 25, 19, 21, 25, 15, 21, 18]),
    #             np.array([ 2. ,  6.6, 11.2, 15.8, 20.4, 25. , 29.6, 34.2, 38.8, 43.4, 48. ]))

    
def test_produce_series_df():
    """just make sure this doesn't fail"""
    sdf, errs = produce_series_df(
        test_df, [Histogram], 'test_df', debug=True)
    ha = sdf['a']['histogram_args']
    _assert_ha(ha)

def test_no_meat():
    """just make sure this doesn't fail based on
    Nearly-constant column with outliers fails to display #264
    https://github.com/paddymul/buckaroo/issues/264
    """
    df = pd.DataFrame({'no_meat': [1] * 400 + [10, 20, 30, 40, 50]})
    sdf, errs = AnalysisPipeline.full_produce_summary_df(df,
        [TypingStats, ComputedDefaultSummaryStats, Histogram, DefaultSummaryStats],
        debug=True)
    assert errs == {}

def test_non_nunique_index():
    """ histograms can fail with non-unique indexes.  non-unique indexes frequently occur as the result of concatting dataframes.  This should not fail
    """
    df = pd.DataFrame({'bad': pd.Series([1,2, pd.NA,  1],
             index= [11000, 11001, 11002,  11000]).astype('Int64')})
    
    sdf, errs = AnalysisPipeline.full_produce_summary_df(df,
        [TypingStats, ComputedDefaultSummaryStats, Histogram, DefaultSummaryStats],
        debug=True)
    assert errs == {}

def test_full_produce_summary_df():
    sdf, errs = AnalysisPipeline.full_produce_summary_df(test_df, [Histogram], debug=True)
    ha = sdf['a']['histogram_args']
    _assert_ha(ha)
    
def test_full_produce_summary_df2():
    sdf, errs = AnalysisPipeline.full_produce_summary_df(
        test_df,
        [TypingStats, ComputedDefaultSummaryStats, Histogram, DefaultSummaryStats],
        debug=True)
    ha = sdf['a']['histogram_args']
    _assert_ha(ha)
    
def test_dfstats_histogram():
    stats = DfStats(
        test_df,
        [TypingStats, ComputedDefaultSummaryStats, Histogram, DefaultSummaryStats],
        'test_df', debug=True)
    sdf = stats.sdf
    
    print(sdf['a'])
    ha = sdf['a']['histogram_args']
    _assert_ha(ha)
