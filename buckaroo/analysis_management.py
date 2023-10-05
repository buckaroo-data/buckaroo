import numpy as np
import pandas as pd
import traceback
from buckaroo.pluggable_analysis_framework import (
    ColAnalysis, order_analysis, check_solvable, NotProvidedException)


FAST_SUMMARY_WHEN_GREATER = 1_000_000


def produce_summary_df(df, ordered_objs, df_name='test_df'):
    """
    takes a dataframe and a list of analyses that have been ordered by a graph sort,
    then it produces a summary dataframe
    """
    errs = {}
    summary_col_dict = {}
    table_hint_col_dict = {}
    #figure out how to add in "index"... but just for table_hints
    for ser_name in df.columns:
        ser = df[ser_name]
        #fixme
        sampled_ser = ser
        summary_ser = pd.Series({}, dtype='object')
        table_hint_dict = {}
        for a_kls in ordered_objs:
            try:
                summary_res = a_kls.summary(ser, summary_ser, ser)
                for k,v in summary_res.items():
                    summary_ser.loc[k] = v
                th_dict = a_kls.table_hints(sampled_ser, summary_ser, table_hint_dict)
                for k,v in th_dict.items():
                    table_hint_dict[k] = v
            except Exception as e:
                print("summary_ser", summary_ser)
                errs[ser_name] = e, a_kls
                traceback.print_exc()
                continue
        summary_col_dict[ser_name] = summary_ser
        table_hint_col_dict[ser_name] = table_hint_dict
    if errs:
        for ser_name, err_kls in errs.items():
            err, kls = err_kls
            print("%r failed on %s with %r" % (kls, ser_name, err))
        print("Reproduce")
        print("from pluggable_analysis import test_ser")
        for ser_name, err_kls in errs.items():
            err, kls = err_kls
            print("%s.summary(test_ser.%s)" % (kls.__name__, ser_name))
    return pd.DataFrame(summary_col_dict), table_hint_col_dict, errs



class NonExistentSummaryRowException(Exception):
    pass



PERVERSE_DF = pd.DataFrame({
    'all_nan': [np.nan] * 10,
    'all_false': [False] * 10,
    'all_True': [True] * 10,
    'mixed_bool': np.concatenate([[True]*5, [False]*5]),
    'mixed_float': np.concatenate([[0.5, np.nan, None], [6]*7]),
    'float': [0.5] *10,
    'int': [8] *10,
    'negative': [-1] *10,
    'UInt32': pd.Series([5]*10, dtype='UInt32')
    })

class AnalsysisPipeline(object):
    """
    manage the ordering of a set of col_analysis objects
    allow for computing summary_stats (and other oberservation sets) based on col_analysis objects
    allow col_anlysis objects to be added
    """
    def __init__(self, analysis_objects, unit_test_objs=True):
        self.summary_stats_display = "all"
        self.unit_test_objs = unit_test_objs
        self.verify_analysis_objects(analysis_objects)

    def process_summary_facts_set(self):
        all_provided = []
        for a_obj in self.ordered_a_objs:
            all_provided.extend(a_obj.provided_summary)
            if a_obj.summary_stats_display:
                self.summary_stats_display = a_obj.summary_stats_display

        self.provided_summary_facts_set = set(all_provided)

        #all is a special value that will dipslay every row
        if self.summary_stats_display and not self.summary_stats_display == "all":
            #verify that we have a way of computing all of the facts we are displaying
            if not self.provided_summary_facts_set.issuperset(set(self.summary_stats_display)):
                raise NonExistentSummaryRowException()

    def verify_analysis_objects(self, analysis_objects):
        self.ordered_a_objs = order_analysis(analysis_objects)
        check_solvable(self.ordered_a_objs)
        self.process_summary_facts_set()
        if self.unit_test_objs:
            self.unit_test()

    def unit_test(self):
        """test a single, or each col_analysis object with a set of commonly difficult series.
        not implemented yet.

        This helps interactive development by doing a smoke test on
        each new iteration of summary stats function.

        """
        try:
            output_df, table_hint_dict, errs = produce_summary_df(PERVERSE_DF, self.ordered_a_objs)
            if len(errs) == 0:
                return True
            return False
        except Exception as e:
            print("analysis pipeline unit_test failed")
            print(e)
            return False


    def process_df(self, input_df):
        output_df, table_hint_dict, errs = produce_summary_df(input_df, self.ordered_a_objs)
        return output_df, table_hint_dict

    def add_analysis(self, new_aobj):
        new_cname = new_aobj.cname()
        new_aobj_set = []
        for aobj in self.ordered_a_objs:
            if aobj.cname() == new_cname:
                continue
            new_aobj_set.append(aobj)
        new_aobj_set.append(new_aobj)
        self.verify_analysis_objects(new_aobj_set)
        if not self.unit_test():
            print("new analysis fails unit tests")
            return False
        return True
            

class DfStats(object):
    '''
    DfStats exists to handle inteligent downampling and applying the ColAnalysis functions
    '''

    def __init__(self, df, col_analysis_objs):
        self.df = self.get_operating_df(df, force_full_eval=False)
        self.col_order = self.df.columns
        self.ap = AnalsysisPipeline(col_analysis_objs)
        self.sdf, self.table_hints = self.ap.process_df(self.df)
        

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
        if self.ap.summary_stats_display == "all":
            return self.sdf
        return self.sdf.loc[self.ap.summary_stats_display]

    def add_analysis(self, a_obj):
        self.ap.add_analysis(a_obj)
        self.sdf, self.table_hints = self.ap.process_df(self.df)

