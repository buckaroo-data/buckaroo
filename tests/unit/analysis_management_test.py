import unittest

from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    ColAnalysis)

from buckaroo.pluggable_analysis_framework.analysis_management import (
    AnalysisPipeline, DfStats,
    #full_produce_summary_df,
    produce_series_df)

from buckaroo.pluggable_analysis_framework.safe_summary_df import (output_full_reproduce)


from buckaroo.customizations.analysis import (TypingStats, DefaultSummaryStats)
from .fixtures import (test_df, df, DistinctCount, Len, DistinctPer, word_only_df,
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

        sdf, errs = produce_series_df(
            test_df, [Len], 'test_df', debug=True)
        #dict(**sdf) makes the types equal and leads to better error messages if there is a problem
        assert dict(**sdf) ==     {
        'empty_na_ser': {
          'col_name': 'empty_na_ser',
            'len': 4,
        },
        'float_nan_ser': {
           'col_name': 'float_nan_ser',
            'len': 4,
        },
        'index': {
           'col_name': 'index',
            'len': 4,
        },
        'normal_int_series': {
           'col_name': 'normal_int_series',
            'len': 4,
        },
    }

        sdf2, errs = produce_series_df(
            test_df, [DistinctCount], 'test_df', debug=True)
        assert dict(**sdf2) == {
            'normal_int_series': {'distinct_count': 4, 'col_name':'normal_int_series'},
            'index':  {'distinct_count': 4,  'col_name':'index'},
            'empty_na_ser': {'distinct_count':0,  'col_name':'empty_na_ser'},
            'float_nan_ser': {'distinct_count':2,  'col_name':'float_nan_ser'}}

        sdf3, errs = produce_series_df(
            test_df, [DistinctCount, DistinctPer], 'test_df', debug=True)
        assert dict(**sdf3) == {
            'normal_int_series': {'distinct_count': 4, 'distinct_per':0, 'col_name':'normal_int_series'},
            'index':             {'distinct_count': 4, 'distinct_per':0, 'col_name':'index'},
            'empty_na_ser':      {'distinct_count': 0, 'distinct_per':0, 'col_name':'empty_na_ser'},
            'float_nan_ser':     {'distinct_count': 2, 'distinct_per':0, 'col_name':'float_nan_ser'}}

    def test_full_produce_summary_df(self):
        """just make sure this doesn't fail"""
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
        """just make sure this doesn't fail"""
        single_col_df = test_df[['empty_na_ser']]
        sdf, errs = AnalysisPipeline.full_produce_summary_df(
            single_col_df, [AlwaysErr], 'test_df', debug=False)

        err_key = list(errs.keys())[0]
        err_val = list(errs.values())[0]
        assert err_key == ('index', 'computed_summary')
        assert err_val[1] ==  AlwaysErr
        #can't compare instances of Exception classes
        # assert errs == {
        #     ('empty_na_ser', 'computed_summary'): (ZeroDivisionError('division by zero'), AlwaysErr)}

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
        self.assertEqual(sdf['tripduration']['foo'], 8)

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
        self.assertEqual(sdf['tripduration']['foo'], 8)
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
        self.assertEqual(sdf2['tripduration']['foo'], 9)
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
        #ab = dfs.presentation_sdf

        #triggers a getter?
        DfStats(word_only_df, [SometimesProvides]).sdf


