
import polars as pl
import numpy as np
from polars import functions as F

from buckaroo.pluggable_analysis_framework.utils import (json_postfix, replace_in_dict)

from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    polars_produce_series_df, PolarsAnalysis)

from buckaroo.pluggable_analysis_framework.polars_analysis_management import PlDfStats
from buckaroo.customizations.polars_analysis import BasicAnalysis, VCAnalysis


class SelectOnlyAnalysis(PolarsAnalysis):

    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
        F.all().quantile(.99).name.map(json_postfix('quin99'))]


def test_produce_series_df():
    """just make sure this doesn't fail"""
    test_df = pl.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
        #'empty_na_ser' : pl.Series([pl.Null] * 4, dtype="Int64"),
        'float_nan_ser' : pl.Series([3.5, np.nan, 4.8, 2.2])
    })

    sdf, errs = polars_produce_series_df(
        test_df, [SelectOnlyAnalysis], 'test_df', debug=True)
    expected = {
        'float_nan_ser':      {'mean': None, 'null_count':  0, 'quin99': None},
        'normal_int_series':  {'mean': 2.5,  'null_count':  0, 'quin99':  4.0}}
    dsdf = replace_in_dict(sdf, [(np.nan, None)])
    assert dsdf == expected


def test_struct():
    """
    structs have caused hard to debug errors.  Make sure they are properly tested
    """
    ser = pl.Series([{'a':5}])
    df = pl.DataFrame({'b': ser, 'normal': [4]})
    dfs = PlDfStats(df, [VCAnalysis, BasicAnalysis], debug=True)
    print(dfs.sdf)
    assert dfs.errs == {}

    
'''

word_only_df = pl.DataFrame({'letters': 'h o r s e'.split(' ')})

df = pl.read_csv('./examples/data/2014-01-citibike-tripdata.csv')

empty_df = pl.DataFrame({})
#empty_df_with_columns = pl.DataFrame({}, columns=[0])
'''
