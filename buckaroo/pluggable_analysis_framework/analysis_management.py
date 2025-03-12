from collections import defaultdict 
import traceback
import warnings

import pandas as pd
import numpy as np


from buckaroo.pluggable_analysis_framework.safe_summary_df import output_full_reproduce, output_reproduce_preamble

from buckaroo.pluggable_analysis_framework.utils import FAST_SUMMARY_WHEN_GREATER, PERVERSE_DF
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    order_analysis, check_solvable)

def produce_series_df(df, ordered_objs, df_name='test_df', debug=False):
    """ just executes the series methods

    """
    errs = {}
    series_stats = defaultdict(lambda: {})

    cols = []
    if hasattr(df, "index"):
        #hack around polars not having indexes"
        cols.append("index")
    cols.extend(df.columns)
    for possib_ser_name in cols:
        if possib_ser_name == "index":
            ser_name = df.index.name or "index"
            ser = df.index.to_series()
        else:
            ser_name = possib_ser_name
            ser = df[ser_name]
        #FIXME: actually sample the series.  waiting until I have time
        #to proeprly benchmark
        sampled_ser = ser
        for a_kls in ordered_objs:
            col_stat_dict = a_kls.provides_defaults.copy()
            try:
                if a_kls.quiet or a_kls.quiet_warnings:
                    if debug is False:
                        warnings.filterwarnings('ignore')
                        
                    col_stat_dict.update(a_kls.series_summary(sampled_ser, ser))
                    warnings.filterwarnings('default')
                else:
                    col_stat_dict.update(a_kls.series_summary(sampled_ser, ser))

                series_stats[ser_name].update(col_stat_dict)
            except Exception as e:
                if not a_kls.quiet:
                    errs[(ser_name, "series_summary")] = e, a_kls
                if debug:
                    traceback.print_exc()
                continue
    return series_stats, errs



def produce_summary_df(df, series_stats, ordered_objs, df_name='test_df', debug=False):
    """
    takes a dataframe and a list of analyses that have been ordered by a graph sort,
    then it produces a summary dataframe
    """
    errs = {}
    summary_col_dict = {}
    cols = []
    if hasattr(df, "index"):
        #hack around polars not having indexes"
        cols.append("index")
    cols.extend(df.columns)
    for possib_ser_name in cols:
        if possib_ser_name == "index":
            ser_name = df.index.name or "index"
        else:
            ser_name = possib_ser_name
    #figure out how to add in "index"... but just for table_hints
    #for ser_name in df.columns:
        #base_summary_dict = series_stats[ser_name]
        base_summary_dict = series_stats.get(ser_name, {})
        for a_kls in ordered_objs:
            try:
                if a_kls.quiet or a_kls.quiet_warnings:
                    if debug is False:
                        warnings.filterwarnings('ignore')
                    summary_res = a_kls.computed_summary(base_summary_dict)
                    warnings.filterwarnings('default')
                else:
                    summary_res = a_kls.computed_summary(base_summary_dict)
                for k,v in summary_res.items():
                    base_summary_dict.update(summary_res)
            except Exception as e:
                if not a_kls.quiet:
                    errs[(ser_name, "computed_summary")] = e, a_kls
                if debug:
                    traceback.print_exc()
                continue
        summary_col_dict[ser_name] = base_summary_dict
    return summary_col_dict, errs


#TODO Figure out how to do proper typing with AnalysisPipeline and the polars subclasses
# We want a TypeVar for DFType and AT.  But the main function, process_df whild still return 3 dicts
#DFT = TypeVar("DFT") #DF Type
#AT =  TypeVar("AT") #Analysis Type
class AnalysisPipeline(object):
    """
    manage the ordering of a set of col_analysis objects
    allow for computing summary_stats (and other oberservation sets) based on col_analysis objects
    allow col_anlysis objects to be added
    """

    #this is only a list to prevent it from being interpretted as an instance method
    #full_produce_func: List[Callable[[DFT, List[AT], str, bool], Any]] =

    @staticmethod
    def full_produce_summary_df(df, ordered_objs, df_name='test_df', debug=False):
        if len(df) == 0:
            return {}, {}

        series_stat_dict, series_errs = produce_series_df(df, ordered_objs, df_name, debug)
        summary_df, summary_errs = produce_summary_df(
            df, series_stat_dict, ordered_objs, df_name, debug)
        series_errs.update(summary_errs)
        try:
            from packaging.version import Version
        except Exception:
            # probably in jupyterlite
            # we have a recent pandas version here, so it's fine to just return the obj
            return summary_df, series_errs
        if Version(pd.__version__) < Version("2.0.7"):
            for col, summary_dict in summary_df.items():
                del_keys = []
                for k,v in summary_dict.items():
                    if isinstance(v, np.datetime64):
                        del_keys.append(k)
                for k in del_keys:
                    del summary_dict[k]
        return summary_df, series_errs

    style_method = None
    
    def __init__(self, analysis_objects, unit_test_objs=True):

        self.summary_stats_display = "all"
        self.unit_test_objs = unit_test_objs
        self.verify_analysis_objects(analysis_objects)

    def process_summary_facts_set(self):
        all_provided = []
        for a_obj in self.ordered_a_objs:
            all_provided.extend(list(a_obj.provides_defaults.keys()))

        self.provided_summary_facts_set = set(all_provided)


    def verify_analysis_objects(self, analysis_objects):
        self.ordered_a_objs = order_analysis(analysis_objects)
        check_solvable(self.ordered_a_objs)
        self.process_summary_facts_set()

    def unit_test(self):
        """test a single, or each col_analysis object with a set of commonly difficult series.
        not implemented yet.

        This helps interactive development by doing a smoke test on
        each new iteration of summary stats function.

        """
        try:
            output_df, errs = self.full_produce_summary_df(PERVERSE_DF, self.ordered_a_objs)
            if len(errs) == 0:
                return True, []
            else:
                return False, errs
        except KeyError:
            pass


    def process_df(self, input_df, debug=False):
        output_df, errs = self.full_produce_summary_df(input_df, self.ordered_a_objs, debug=debug)
        return output_df, errs

    def add_analysis(self, new_aobj):
        new_cname = new_aobj.cname()
        new_aobj_set = []
        for aobj in self.ordered_a_objs:
            if aobj.cname() == new_cname:
                continue
            new_aobj_set.append(aobj)
        new_aobj_set.append(new_aobj)
        self.verify_analysis_objects(new_aobj_set)
        passed_unit_test, errs = self.unit_test()
        if passed_unit_test is False:
            return False, errs
        return True, []
            

class DfStats(object):
    '''
    DfStats exists to handle inteligent downampling and applying the ColAnalysis functions
    '''

    ap_class = AnalysisPipeline

    @classmethod
    def verify_analysis_objects(kls, col_analysis_objs):
        kls.ap_class(col_analysis_objs)

    def __init__(self, df_stats_df, col_analysis_objs, operating_df_name=None, debug=False):
        self.df = self.get_operating_df(df_stats_df, force_full_eval=False)
        self.col_order = self.df.columns
        self.ap = self.ap_class(col_analysis_objs)
        self.operating_df_name = operating_df_name
        self.debug = debug

        self.sdf, self.errs = self.ap.process_df(self.df, self.debug)
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)
        
    def get_operating_df(self, df, force_full_eval):
        rows = len(df)
        cols = len(df.columns)
        item_count = rows * cols

        if item_count > FAST_SUMMARY_WHEN_GREATER:
            return df.sample(np.min([50_000, len(df)]))
        else:
            return df

    @property
    def presentation_sdf(self):
        raise Exception("deprecated")

    def add_analysis(self, a_obj):
        passed_unit_tests, ut_errs = self.ap.add_analysis(a_obj)
        #if you're adding analysis interactively, of course you want debug info... I think
        self.sdf, errs = self.ap.process_df(self.df, debug=True)
        if passed_unit_tests is False:
            print("Unit tests failed")
        if errs:
            print("Errors on original dataframe")

        if ut_errs or errs:
            output_reproduce_preamble()
        if ut_errs:
            # setting debug=False here because we're already printing reproduce instructions, let the users produce their own stacktrace.. I think
            ut_summary_df, ut_errs2 = produce_summary_df(
                PERVERSE_DF, self.ap.ordered_a_objs, debug=False)
            output_full_reproduce(ut_errs, ut_summary_df, "PERVERSE_DF")
        if errs:
            output_full_reproduce(errs, self.sdf, self.operating_df_name)
