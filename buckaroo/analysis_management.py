import sys
import traceback

import numpy as np
import pandas as pd
from buckaroo.pluggable_analysis_framework import (
    ColAnalysis, order_analysis, check_solvable, NotProvidedException)
from buckaroo.serialization_utils import pd_py_serialize, pick, d_update

FAST_SUMMARY_WHEN_GREATER = 1_000_000

PERVERSE_DF = pd.DataFrame({
    'all_nan': [np.nan] * 10,
    'all_false': [False] * 10,
    'all_True': [True] * 10,
    'mixed_bool': np.concatenate([[True]*5, [False]*5]),
    'mixed_float': np.concatenate([[0.5, np.nan, None], [6]*7]),
    'float': [0.5]*10,
    'int': [8] *10,
    'negative': [-1]*10,
    'UInt32': pd.Series([5]*10, dtype='UInt32'),
    'UInt8None':pd.Series([None] * 10, dtype='UInt8')
    })


BASE_COL_HINT = {
    'type':'string',
    'is_numeric': False,
    'is_integer': None,
    'min_digits':None,
    'max_digits':None,
    'histogram': []}



def get_df_name(df, level=0):
    """ looks up the call stack until it finds the variable with this name"""
    if level == 0:
        _globals = globals()
    elif level < 60:
        try:
            call_frame = sys._getframe(level)
            _globals = call_frame.f_globals
        except ValueError:
            return None #we went to far up the stacktrace to a non-existent frame
    else:
        return None

    name_possibs = [x for x in _globals.keys() if _globals[x] is df]
    if name_possibs:
        return name_possibs[0]
    else:
        #+2 because the function is recursive, and we need to skip over this frame
        return get_df_name(df, level + 2)

def safe_summary_df(base_summary_df, index_list):
    #there are instances where not all indexes of the summary_df will
    #be available, because there was no valid data to produce those
    #indexes. This fixes them and explicitly. Empty rows will have NaN
    return pd.DataFrame(base_summary_df, index_list)

def reproduce_summary(ser_name, kls, summary_df, err, operating_df_name):
    ssdf = safe_summary_df(summary_df, kls.requires_summary)
    summary_ser = ssdf[ser_name]
    minimal_summary_dict = pick(summary_ser, kls.requires_summary)
    sum_ser_repr = "pd.Series(%s)" % pd_py_serialize(minimal_summary_dict)

    f = "{kls}.summary({df_name}['{ser_name}'], {summary_ser_repr}, {df_name}['{ser_name}']) # {err_msg}"
    print(f.format(
        kls=kls.cname(), df_name=operating_df_name, ser_name=ser_name,
        summary_ser_repr=sum_ser_repr, err_msg=err))

def output_reproduce_preamble():
    print("#Reproduction code")
    print("#" + "-" * 80)
    print("from buckaroo.analysis_management import PERVERSE_DF")

def output_full_reproduce(errs, summary_df, df_name):
    if len(errs) == 0:
        raise Exception("output_full_reproduce called with 0 len errs")

    try:
        for ser_name, err_kls in errs.items():
            err, kls = err_kls
            reproduce_summary(ser_name, kls, summary_df, err, df_name)
    except Exception as e:
        #this is tricky stuff that shouldn't error, I want these stack traces to escape being caught
        traceback.print_exc()




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
        #FIXME: actually sample the series.  waiting until I have time
        #to proeprly benchmark

        sampled_ser = ser
        summary_ser = pd.Series({}, dtype='object')
        table_hint_dict = {}
        for a_kls in ordered_objs:
            try:
                if a_kls.quiet or a_kls.quiet_warnings:
                    warnings.filterwarnings('ignore')
                    summary_res = a_kls.summary(ser, summary_ser, ser)
                    warnings.filterwarnings('default')
                else:
                    summary_res = a_kls.summary(ser, summary_ser, ser)
                for k,v in summary_res.items():
                    summary_ser.loc[k] = v
            except Exception as e:
                if not a_kls.quiet:
                    errs[ser_name] = e, a_kls
                continue
        summary_col_dict[ser_name] = summary_ser

        table_hint_col_dict[ser_name] = pick(
            d_update(BASE_COL_HINT, summary_ser.to_dict()),
            BASE_COL_HINT.keys())
    summary_df = pd.DataFrame(summary_col_dict)
    table_hints = table_hint_col_dict
    return summary_df, table_hints, errs

class NonExistentSummaryRowException(Exception):
    pass

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
            all_provided.extend(a_obj.provides_summary)
            if a_obj.summary_stats_display:
                self.summary_stats_display = a_obj.summary_stats_display

        self.provided_summary_facts_set = set(all_provided)

        #all is a special value that will dipslay every row
        if self.summary_stats_display and not self.summary_stats_display == "all":
            #verify that we have a way of computing all of the facts we are displaying
            if not self.provided_summary_facts_set.issuperset(set(self.summary_stats_display)):
                missing = set(self.summary_stats_display) - set(self.provided_summary_facts_set)
                raise NonExistentSummaryRowException(missing)

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
            output_df, table_hint_dict, errs = produce_summary_df(PERVERSE_DF, self.ordered_a_objs)
            if len(errs) == 0:
                return True, []
            else:
                return False, errs
        except KeyError:
            pass


    def process_df(self, input_df):
        output_df, table_hint_dict, errs = produce_summary_df(input_df, self.ordered_a_objs)
        return output_df, table_hint_dict, errs

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

    def __init__(self, df_stats_df, col_analysis_objs, operating_df_name=None):
        self.df = self.get_operating_df(df_stats_df, force_full_eval=False)
        self.col_order = self.df.columns
        self.ap = AnalsysisPipeline(col_analysis_objs)
        self.operating_df_name = operating_df_name

        self.sdf, self.table_hints, errs = self.ap.process_df(self.df)
        if errs:
            output_full_reproduce(errs, self.sdf, operating_df_name)
        
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
        return safe_summary_df(self.sdf, self.ap.summary_stats_display)

    def add_analysis(self, a_obj):
        passed_unit_tests, ut_errs = self.ap.add_analysis(a_obj)
        self.sdf, self.table_hints, errs = self.ap.process_df(self.df)
        if passed_unit_tests == False:
            print("Unit tests failed")
        if errs:
            print("Errors on original dataframe")

        if ut_errs or errs:
            output_reproduce_preamble()
        if ut_errs:
            ut_summary_df, _unused_table_hint_dict, ut_errs2 = produce_summary_df(
                PERVERSE_DF, self.ap.ordered_a_objs)
            output_full_reproduce(ut_errs, ut_summary_df, "PERVERSE_DF")
        if errs:
            output_full_reproduce(errs, self.sdf, self.operating_df_name)
