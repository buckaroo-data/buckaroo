import traceback

import polars as pl

from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts


from .pluggable_analysis_framework import ColAnalysis
from .analysis_management import (produce_summary_df, AnalysisPipeline, DfStats)
from .utils import (BASE_COL_HINT)
from buckaroo.serialization_utils import pick, d_update
from buckaroo.pluggable_analysis_framework.safe_summary_df import safe_summary_df
from typing import Mapping, Any, Callable, Tuple, List, MutableMapping



class PolarsAnalysis(ColAnalysis):
    select_clauses:List[pl.Expr] = []
    column_ops: Mapping[str, Tuple[List[pl.PolarsDataType], Callable[[pl.Series], Any]]] = {}

def normalize_polars_histogram(ph:pl.DataFrame, ser:pl.Series):
    edges = ph['break_point'].to_list()
    edges[0], edges[-1] = ser.min(), ser.max()
    #col_series.hist(bin_count=10)
    col_only_df = ph.select(pl.col("^.*_count$"))
    counts = col_only_df[col_only_df.columns[0]].to_list()
    #counts = ph['_count'].to_list()
    return counts[1:], edges


def produce_series_df(df:pl.DataFrame,
                      unordered_objs:List[PolarsAnalysis],
                      df_name:str='test_df', debug:bool=False):
    """ just executes the series methods

    """
    errs: MutableMapping[str, str] = {}
    all_clauses = []
    for obj in unordered_objs:
        all_clauses.extend(obj.select_clauses)
    try:
        result_df = df.lazy().select(all_clauses).collect()
    except Exception:
        if debug:
            df.write_parquet('error.parq')
        traceback.print_exc()
        return dict([[k, {}] for k in df.columns]), {}
    summary_dict = split_to_dicts(result_df)

    for pa in unordered_objs:
        for measure_name, action_tuple in pa.column_ops.items():
            col_selector, func = action_tuple
            if col_selector == "all":
                sub_df = df.select(pl.all())
            else:
                sub_df = df.select(pl.col(col_selector))
            for col in sub_df.columns:
                summary_dict[col][measure_name] = func(df[col])
                pass
    return summary_dict, errs

def extract_table_hint(summary_dict, columns):
    table_hint_col_dict = {}
    for ser_name in columns:
        table_hint_col_dict[ser_name] = pick(
            d_update(BASE_COL_HINT, summary_dict[ser_name]),
            BASE_COL_HINT.keys())
    return table_hint_col_dict
    
def full_produce_summary_df(
        df:pl.DataFrame, ordered_objs:List[PolarsAnalysis],
        df_name:str='test_df', debug:bool=False):
    series_stat_dict, series_errs = produce_series_df(df, ordered_objs, df_name, debug)
    summary_dict, summary_errs = produce_summary_df(
        df, series_stat_dict, ordered_objs, df_name, debug)
    series_errs.update(summary_errs)
    table_hint_col_dict = extract_table_hint(summary_dict, df.columns)
    return summary_dict, table_hint_col_dict, series_errs



class PolarsAnalysisPipeline(AnalysisPipeline):
    """
    manage the ordering of a set of col_analysis objects
    allow for computing summary_stats (and other oberservation sets) based on col_analysis objects
    allow col_anlysis objects to be added
    """
    full_produce_func = [full_produce_summary_df]

    def add_analysis(self, new_aobj):
        new_cname = new_aobj.cname()
        new_aobj_set = []
        for aobj in self.ordered_a_objs:
            if aobj.cname() == new_cname:
                continue
            new_aobj_set.append(aobj)
        new_aobj_set.append(new_aobj)
        self.verify_analysis_objects(new_aobj_set)

        # passed_unit_test, errs = self.unit_test()
        # if passed_unit_test is False:
        #     return False, errs
        return True, []
            

class PlDfStats(DfStats):
    '''
    DfStats exists to handle inteligent downampling and applying the ColAnalysis functions
    '''
    ap_class = PolarsAnalysisPipeline
    
    @property
    def presentation_sdf(self):
        import pandas as pd
        if self.ap.summary_stats_display == "all":
            return pd.DataFrame(self.sdf)
        return safe_summary_df(self.sdf, self.ap.summary_stats_display)
