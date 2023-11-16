import unittest
import pytest

from buckaroo.pluggable_analysis_framework import (
    ColAnalysis)

from buckaroo.analysis_management import (
    AnalsysisPipeline, produce_summary_df, NonExistentSummaryRowException,
    DfStats)

from buckaroo.analysis import (TypingStats, DefaultSummaryStats, ColDisplayHints)
from .fixtures import (test_df, df, DistinctCount, Len, DistinctPer, DCLen, word_only_df)

class DumbTableHints(ColAnalysis):
    provides_summary = [
        'is_numeric', 'is_integer', 'min_digits', 'max_digits', 'histogram']

    @staticmethod
    def summary(sampled_ser, summary_ser, ser):
        return {'is_numeric':True,
                'is_integer':False,
                'min_digits':3,
                'max_digits':10,
                'histogram': []}


class TestAnalysisPipeline(unittest.TestCase):
    def test_produce_summary_df(self):
        produce_summary_df(test_df, [DistinctCount, Len, DistinctPer], 'test_df')

    def test_produce_summary_df_hints(self):
        #this test should be ported over to the full basic_widget test with actaul verificaiton of values
        
        summary_df, hints, errs = produce_summary_df(
            test_df, [DumbTableHints], 'test_df')

        for col, hint_obj in hints.items():
            #hacky replication of typescript types, just basically testing that hints are constructed properly
            if hint_obj['is_numeric'] == False:
                assert 'histogram' in hint_obj.keys()
            else:
                expected_set = set(
                    ['is_numeric', 'is_integer', 'min_digits', 'max_digits', 'type', 'formatter', 'histogram'])
                assert expected_set == set(hint_obj.keys())

    def test_pipeline_base(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        #just verify that there are no errors
        ap.process_df(df)

    def test_add_aobj(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def summary(sampled_ser, summary_ser, ser):
                return dict(foo=8)
        assert ap.add_analysis(Foo) == (True, []) #verify no errors thrown
        sdf, _unused, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf.loc['foo']['tripduration'], 8)

    def test_add_buggy_aobj(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def summary(sampled_ser, summary_ser, ser):
                1/0 #throw an error
                return dict(foo=8)
        unit_test_results, errs = ap.add_analysis(Foo)
        
        assert unit_test_results == False

    def test_replace_aobj(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def summary(sampled_ser, summary_ser, ser):
                return dict(foo=8)
        ap.add_analysis(Foo)
        sdf, _unused, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf.loc['foo']['tripduration'], 8)
        #18 facts returned about tripduration
        self.assertEqual(len(sdf['tripduration']), 18)
        #Create an updated Foo that returns 9
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']

            @staticmethod
            def summary(sampled_ser, summary_ser, ser):
                return dict(foo=9)
        ap.add_analysis(Foo)
        sdf2, _unused, _unused_errs = ap.process_df(df)
        self.assertEqual(sdf2.loc['foo']['tripduration'], 9)
        #still 18 facts returned about tripduration
        self.assertEqual(len(sdf2['tripduration']), 18)
        #Create an updated Foo that returns 9

    def test_summary_stats_display(self):
        ap = AnalsysisPipeline([TypingStats])
        self.assertEqual(ap.summary_stats_display, "all")
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        print(ap.summary_stats_display)
        self.assertTrue("dtype" in ap.summary_stats_display)

    def test_add_summary_stats_display(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']
            summary_stats_display = ['foo']

        ap.add_analysis(Foo)
        self.assertEquals(ap.summary_stats_display, ['foo'])

    def test_invalid_summary_stats_display_throws(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
        class Foo(ColAnalysis):
            provides_summary = ['foo']
            requires_summary = ['length']
            summary_stats_display = ['not_provided']

        def bad_add():
            ap.add_analysis(Foo)            

        self.assertRaises(NonExistentSummaryRowException, bad_add)

    def test_invalid_summary_stats_display_throws(self):
        ap = AnalsysisPipeline([TypingStats, DefaultSummaryStats])
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
    def summary(sampled_ser, summary_ser, ser):
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
        dfs = DfStats(word_only_df, [SometimesProvides])
        ab = dfs.presentation_sdf


