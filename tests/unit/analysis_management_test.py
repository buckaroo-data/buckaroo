import unittest
import warnings

import pytest
from buckaroo.pluggable_analysis_framework.col_analysis import (
    ColAnalysis)

from buckaroo.pluggable_analysis_framework.analysis_management import (
    AnalysisPipeline, DfStats,
    #full_produce_summary_df,
    produce_series_df)

from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import NotProvidedException
from buckaroo.pluggable_analysis_framework.safe_summary_df import (output_full_reproduce)


from buckaroo.customizations.analysis import (TypingStats, DefaultSummaryStats)
from tests.unit.test_utils import assert_dict_eq
from .fixtures import (test_df, df, DistinctCount, Len, DistinctPer, test_multi_index_df, word_only_df,
                       empty_df, empty_df_with_columns)

class DumbTableHints(ColAnalysis):
    provides_summary = [
        'is_numeric', 'is_integer', 'min_digits', 'max_digits', 'histogram']

    provides_defaults = {
        'is_numeric':False, 'is_integer':False, 'histogram':[]}
    @staticmethod
    def computed_summary(summary_dict):
        return {'is_numeric':True,
                'is_integer':False,
                'histogram': []}

class AlwaysErr(ColAnalysis):
    provides_defaults = {'foo':0}

    @staticmethod
    def computed_summary(summary_dict):
        1/0

class AlwaysErrButQuiet(ColAnalysis):
    """
      quiet=True makes analysis_management swallow the errors and return the defaults
      """
    provides_defaults = {'foo':30}
    quiet = True

    @staticmethod
    def computed_summary(summary_dict):
        1/0

class AlwaysWarn(ColAnalysis):
    provides_defaults = {'foo':0}

    @staticmethod
    def series_summary(sampled_ser, ser):

        warnings.warn("AlwayWarn", UserWarning)
        return {'foo': 5}



class DependsA(ColAnalysis):

    provides_defaults = { 'b':'asdf'}
    requires_summary = ['a']
    @staticmethod
    def computed_summary(summary_dict):
        if summary_dict.get('a',False) == 'asdf':
            raise Exception("DependsA expected 'a' in summary_dict, it wasn't there")
        return { 'b':'bar'}


            
class ProvidesAComputed(ColAnalysis):

    provides_defaults = { 'a':'asdf'}
    @staticmethod
    def computed_summary(summary_dict):
        return { 'a':'bar'}



class TestAnalysisPipeline(unittest.TestCase):

    def test_provides_ordering(self):
        """Make sure computed_summary of provides called before it is required.
        """

        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            test_df, [ProvidesAComputed, DependsA], 'test_df', debug=True)
        assert errs == {}



    def test_produce_series_df(self):
        """just make sure this doesn't fail"""

        sdf, _errs = produce_series_df(
            test_df, [Len, Len], 'test_df', debug=True)
        #dict(**sdf) makes the types equal and leads to better error messages if there is a problem
        assert_dict_eq({
            'a': {
                'orig_col_name': 'normal_int_series',
                'len': 4, 'rewritten_col_name':'a'
            },
            'b': {
                'orig_col_name': 'empty_na_ser',
                'len': 4,  'rewritten_col_name':'b'
            },
            'c': {
                'orig_col_name': 'float_nan_ser',
                'len': 4, 'rewritten_col_name':'c'
            },
        },
                       sdf)


    maxDiff = None
    def test_produce_series_df2(self):
        """just make sure this doesn't fail"""


        sdf2, _errs = produce_series_df(
            test_df, [DistinctCount], 'test_df', debug=True)
        assert_dict_eq({
            'a': {'distinct_count': 4, 'orig_col_name':'normal_int_series', 'rewritten_col_name':'a'},
            'b': {'distinct_count':0,  'orig_col_name':'empty_na_ser', 'rewritten_col_name':'b'},
            'c': {'distinct_count':2,  'orig_col_name':'float_nan_ser', 'rewritten_col_name':'c'}},
        sdf2)


    def test_produce_series_df3(self):
        """just make sure this doesn't fail,

          this technically needs Len, but because of
          provides_defaults, exceptions are caught and the defaults
          are subsitututed

        """
        sdf3, _errs = produce_series_df(
        test_df, [DistinctCount, DistinctPer], 'test_df', debug=True)

        assert_dict_eq({
            'a': {'distinct_count': 4, 'distinct_per':0, 'orig_col_name':'normal_int_series', 'rewritten_col_name':'a'},
            'b': {'distinct_count': 0, 'distinct_per':0, 'orig_col_name':'empty_na_ser',      'rewritten_col_name':'b'},
            'c': {'distinct_count': 2, 'distinct_per':0, 'orig_col_name':'float_nan_ser',     'rewritten_col_name':'c'}},
        sdf3)

    def Xtest_produce_series_debug(self):
        """
          I can't currently get this test to work properly
          I want to make sure there are no warnings emitted when Debug=False

          I'm pretty sure this is what happens in the notebook. I'm not sure if pytest is doing something funky
          
          """

        with warnings.catch_warnings(record=True) as _warn_record_1:
            _sdf3, _errs = produce_series_df(
                test_df, [AlwaysWarn], 'test_df', debug=False)
            
        # print(_warn_record_1)
        # assert _warn_record_1 == []
        with pytest.warns() as record:
            _sdf4, _errs = produce_series_df(
                test_df, [AlwaysWarn], 'test_df', debug=True)
        assert len(record) == 1
        
    def test_produce_series_multiindex_cols_df(self):
        """just make sure this doesn't fail"""

        sdf, _errs = produce_series_df(
            test_multi_index_df, [Len], 'test_df', debug=True)
        assert sdf['a'] == {'orig_col_name': ('foo', 'normal_int_series'), 'len': 4, 'rewritten_col_name':'a'}

        
    def test_full_produce_summary_df(self):
        """just make sure this doesn't fail"""
        res = DistinctCount.series_summary(test_df['normal_int_series'], test_df['normal_int_series'])
        assert res == {'distinct_count':4}
        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            test_df, [DistinctCount, Len, DistinctPer], 'test_df', debug=True)
        assert errs == {}

    def test_full_produce_summary_df_empy(self):
        """just make sure this doesn't fail"""
        
        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            empty_df, [DistinctCount, Len, DistinctPer], 'test_df', debug=True)
        assert errs == {}

    def test_full_produce_summary_df_empy2(self):
        """just make sure this doesn't fail"""
        
        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            empty_df_with_columns, [DistinctCount, Len, DistinctPer], 'test_df', debug=True)
        assert errs == {}

    def test_full_produce_summary_df_errs(self):
        """just make sure this doesn't fail with a stack trace, but
        that errors are properly caught and returned"""
        single_col_df = test_df[['empty_na_ser']]
        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            single_col_df, [AlwaysErr], 'test_df', debug=False)


        err_key = list(errs.keys())[0]
        err_val = list(errs.values())[0]
        #assert err_key == ('empty_na_ser', 'computed_summary')
        assert err_key == ('a', 'computed_summary')
        assert err_val[1] ==  AlwaysErr
        #can't compare instances of Exception classes
        # assert errs == {
        #     ('empty_na_ser', 'computed_summary'): (ZeroDivisionError('division by zero'), AlwaysErr)}

    def test_full_produce_summary_df_errs_quiet(self):
        """just make sure this doesn't fail"""
        single_col_df = test_df[['empty_na_ser']]
        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            single_col_df, [AlwaysErrButQuiet], 'test_df', debug=False)
        assert len(errs) == 0

    def test_output_full_reproduce(self):
        errs = {
            ('empty_na_ser', 'computed_summary'): (ZeroDivisionError('division by zero'), AlwaysErr)}
        output_full_reproduce(errs, {'bar':8}, 'testing_df')
        
    def test_pipeline_base(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        #just verify that there are no errors
        ap.process_df(df)

    def test_add_aobj(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_defaults = {'foo':0}
            requires_summary = ['length']

            @staticmethod
            def computed_summary(summary):
                return dict(foo=8)
        assert ap.add_analysis(Foo) == (True, []) #verify no errors thrown
        sdf, _unused_errs = ap.process_df(df)
        #self.assertEqual(sdf['tripduration']['foo'], 8)
        self.assertEqual(sdf['a']['foo'], 8)

    def test_add_buggy_aobj(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_defaults = {'foo':0}
            requires_summary = ['length']

            @staticmethod
            def computed_summary(summary_dict):
                1/0 #throw an error
                return dict(foo=8)
        unit_test_results, errs = ap.add_analysis(Foo)
        
        assert unit_test_results is False

    def test_replace_aobj(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_defaults = {'foo':0}
            requires_summary = ['length']

            @staticmethod
            def computed_summary(bar):
                return dict(foo=8)
        ap.add_analysis(Foo)
        sdf, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf['a']['foo'], 8)
        #18 facts returned about tripduration
        #FIXME
        #self.assertEqual(len(sdf['tripduration']), 18)
        #Create an updated Foo that returns 9
        class Foo(ColAnalysis):
            provides_defaults = {'foo':0}
            requires_summary = ['length']

            @staticmethod
            def computed_summary(bar):
                return dict(foo=9)
        ap.add_analysis(Foo)
        sdf2, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf2['a']['foo'], 9)
        #still 18 facts returned about tripduration
        #self.assertEqual(len(sdf2['tripduration']), 18)
        #Create an updated Foo that returns 9


class SometimesProvides(ColAnalysis):
    provides_defaults = {'conditional_on_dtype':'xcvz'}

    summary_stats_display = ['conditional_on_dtype']
    
    @staticmethod
    def series_summary(ser, ser2):
        import pandas as pd
        is_numeric = pd.api.types.is_numeric_dtype(ser)
        if is_numeric:
            return dict(conditional_on_dtype=True)
        return {}

class TestDfStats(unittest.TestCase):
    def test_dfstats_sometimes_present(self):
        """many ColAnalysis objects are written such that they only
        provide stats for certain dtypes. This used to cause
        instantiation failures. This test verifies that there are no
        stack traces. The alternative would be to have ColAnalyis
        objects always return every key, even if NA. That's a less
        natural style to write analyis code.

        Possible future improvement is to run through PERVERSE_DF and
        verify that each ColAnalyis provides its specified value as
        non NA at least once

        """
        #dfs = DfStats(word_only_df, [SometimesProvides])

        #triggers a getter?
        DfStats(word_only_df, [SometimesProvides]).sdf



    def test_dfstats_return(self):
        """
          test the actual retuns values from dfstats
          """
        dfs = DfStats(test_df, [Len, DistinctCount, DistinctPer], 'test_df', debug=True)

        assert_dict_eq({
            'a': {'distinct_count': 4, 'distinct_per':1.0, 'len': 4,
                  'orig_col_name':'normal_int_series', 'rewritten_col_name':'a'},
            'b': {'distinct_count': 0, 'distinct_per':0, 'len': 4,
                  'orig_col_name':'empty_na_ser', 'rewritten_col_name':'b'},
            'c': {'distinct_count': 2, 'distinct_per':0.5, 'len': 4,
                  'orig_col_name':'float_nan_ser', 'rewritten_col_name':'c'}},
        dfs.sdf)


    def test_dfstats_Missing_Analysis(self):
        # this is missing "len" and should throw an exception
        with pytest.raises(NotProvidedException):
            _dfs = DfStats(test_df, [DistinctCount, DistinctPer], 'test_df', debug=True)

