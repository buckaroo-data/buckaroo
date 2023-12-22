import unittest

from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    ColAnalysis)

from buckaroo.pluggable_analysis_framework.analysis_management import (
    AnalysisPipeline, NonExistentSummaryRowException, DfStats,
    #produce_summary_df, #test this too

    full_produce_summary_df, produce_series_df)

from buckaroo.pluggable_analysis_framework.safe_summary_df import (output_full_reproduce)


from buckaroo.customizations.analysis import (TypingStats, DefaultSummaryStats)
from .fixtures import (test_df, df, DistinctCount, Len, DistinctPer, word_only_df,
                       empty_df, empty_df_with_columns)

class DumbTableHints(ColAnalysis):
    provides_summary = [
        'is_numeric', 'is_integer', 'min_digits', 'max_digits', 'histogram']

    @staticmethod
    def computed_summary(summary_dict):
        return {'is_numeric':True,
                'is_integer':False,
                'min_digits':3,
                'max_digits':10,
                'histogram': []}

class AlwaysErr(ColAnalysis):
    provides_summary = ['foo']

    @staticmethod
    def computed_summary(summary_dict):
        1/0

class TestAnalysisPipeline(unittest.TestCase):

    def test_produce_series_df(self):
        """just make sure this doesn't fail"""

        sdf, errs = produce_series_df(
            test_df, [Len], 'test_df', debug=True)
        ld = {'len':4}
        assert sdf == {'normal_int_series': ld, 'empty_na_ser': ld, 'float_nan_ser': ld}

        sdf2, errs = produce_series_df(
            test_df, [DistinctCount], 'test_df', debug=True)
        assert sdf2 == {'normal_int_series': {'distinct_count': 4},
                        'empty_na_ser': {'distinct_count':0}, 'float_nan_ser': {'distinct_count':2}}

        sdf3, errs = produce_series_df(
            test_df, [DistinctCount, DistinctPer], 'test_df', debug=True)
        assert sdf3 == {'normal_int_series': {'distinct_count': 4},
                        'empty_na_ser': {'distinct_count':0}, 'float_nan_ser': {'distinct_count':2}}

    def test_full_produce_summary_df(self):
        """just make sure this doesn't fail"""
        sdf, th, errs = full_produce_summary_df(
            test_df, [DistinctCount, Len, DistinctPer], 'test_df', debug=True)
        assert errs == {}

    def test_full_produce_summary_df_empy(self):
        """just make sure this doesn't fail"""
        
        sdf, th, errs = full_produce_summary_df(
            empty_df, [DistinctCount, Len, DistinctPer], 'test_df', debug=True)
        assert errs == {}

    def test_full_produce_summary_df_empy2(self):
        """just make sure this doesn't fail"""
        
        sdf, th, errs = full_produce_summary_df(
            empty_df_with_columns, [DistinctCount, Len, DistinctPer], 'test_df', debug=True)
        assert errs == {}

    def test_full_produce_summary_df_errs(self):
        """just make sure this doesn't fail"""
        single_col_df = test_df[['empty_na_ser']]
        sdf, th, errs = full_produce_summary_df(
            single_col_df, [AlwaysErr], 'test_df', debug=False)

        err_key = list(errs.keys())[0]
        err_val = list(errs.values())[0]
        assert err_key == ('empty_na_ser', 'computed_summary')
        assert err_val[1] ==  AlwaysErr
        #can't compare instances of Exception classes
        # assert errs == {
        #     ('empty_na_ser', 'computed_summary'): (ZeroDivisionError('division by zero'), AlwaysErr)}

    def test_output_full_reproduce(self):
        errs = {
            ('empty_na_ser', 'computed_summary'): (ZeroDivisionError('division by zero'), AlwaysErr)}
        output_full_reproduce(errs, {'bar':8}, 'testing_df')
        
    def test_produce_summary_df_hints(self):
        #this test should be ported over to the full basic_widget test with actaul verificaiton of values
        
        summary_df, hints, errs = full_produce_summary_df(
            test_df, [DumbTableHints], 'test_df')

        for col, hint_obj in hints.items():
            #hacky replication of typescript types, just basically testing that hints are constructed properly
            if hint_obj['is_numeric'] is False:
                assert 'histogram' in hint_obj.keys()
            else:
                expected_set = set(
                    ['is_numeric', 'is_integer', 'min_digits', 'max_digits', 'type', 'formatter', 'histogram'])
                assert expected_set == set(hint_obj.keys())

    def test_pipeline_base(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        #just verify that there are no errors
        ap.process_df(df)

    def test_add_aobj(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def computed_summary(summary):
                return dict(foo=8)
        assert ap.add_analysis(Foo) == (True, []) #verify no errors thrown
        sdf, _unused, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf['tripduration']['foo'], 8)

    def test_add_buggy_aobj(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
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
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def computed_summary(bar):
                return dict(foo=8)
        ap.add_analysis(Foo)
        sdf, _unused, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf['tripduration']['foo'], 8)
        #18 facts returned about tripduration
        #FIXME
        #self.assertEqual(len(sdf['tripduration']), 18)
        #Create an updated Foo that returns 9
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def computed_summary(bar):
                return dict(foo=9)
        ap.add_analysis(Foo)
        sdf2, _unused, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf2['tripduration']['foo'], 9)
        #still 18 facts returned about tripduration
        #self.assertEqual(len(sdf2['tripduration']), 18)
        #Create an updated Foo that returns 9

    def test_summary_stats_display(self):
        class AlwaysFoo(ColAnalysis):
            provides_summary = ['foo']
            summary_stats_display = ['foo']

            @staticmethod
            def computed_summary(summary_dict):
                return dict(foo=3)

        class AlwaysBar(ColAnalysis):
            provides_summary = ['bar']
            summary_stats_display = ['bar']

            @staticmethod
            def computed_summary(summary_dict):
                return dict(bar=3)

        ap = AnalysisPipeline([AlwaysFoo])
        self.assertEqual(ap.summary_stats_display, ["foo"])
        ap.add_analysis(AlwaysBar)
        assert ap.summary_stats_display == ["bar"]

        ap2 = AnalysisPipeline([AlwaysFoo, AlwaysBar])
        assert ap2.ordered_a_objs == [AlwaysFoo, AlwaysBar]
        assert ap2.summary_stats_display == ["bar"]

    def test_summary_stats_display2(self):
        """
        defines vagaries of dependent analysis and sumary stats
        """
        class AlwaysFoo(ColAnalysis):
            provides_summary = ['foo']
            summary_stats_display = ['foo']

            @staticmethod
            def computed_summary(summary_dict):
                return dict(foo=3)
        class DependsFoo(ColAnalysis):
            provides_summary = ['xoq']
            requires_summary = ['foo']
            summary_stats_display = ['xoq']

            @staticmethod
            def computed_summary(summary_dict):
                return dict(xoq=3)


        class AlwaysBar(ColAnalysis):
            provides_summary = ['bar']
            summary_stats_display = ['bar']

            @staticmethod
            def computed_summary(summary_dict):
                return dict(bar=3)

        ap2 = AnalysisPipeline([AlwaysFoo, AlwaysBar])
        self.assertEqual(ap2.summary_stats_display, ["bar"])
        ap2.add_analysis(DependsFoo)
        self.assertEqual(ap2.summary_stats_display, ["xoq"])

        ap = AnalysisPipeline([DependsFoo, AlwaysFoo])
        self.assertEqual(ap.summary_stats_display, ["xoq"])
        ap2.add_analysis(AlwaysBar)
        #Always Bar doesn't depend on anything so it doesn't replace xoq in summary_stats_display
        assert ap.summary_stats_display == ["xoq"]

    def test_add_summary_stats_display(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']
            summary_stats_display = ['foo']

        ap.add_analysis(Foo)
        self.assertEquals(ap.summary_stats_display, ['foo'])

    def test_invalid_summary_stats_display_throws(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']
            summary_stats_display = ['not_provided']

        def bad_add():
            ap.add_analysis(Foo)            

        self.assertRaises(NonExistentSummaryRowException, bad_add)

    def test_invalid_summary_stats_display_throws2(self):
        ap = AnalysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']
            summary_stats_display = ['not_provided']

        def bad_add():
            ap.add_analysis(Foo)            

        self.assertRaises(NonExistentSummaryRowException, bad_add)



class SometimesProvides(ColAnalysis):
    provides_summary = ['conditional_on_dtype']

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
        DfStats(word_only_df, [SometimesProvides]).presentation_sdf


