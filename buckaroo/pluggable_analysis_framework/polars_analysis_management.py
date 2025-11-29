from typing_extensions import TypeAlias

import polars as pl

from buckaroo.df_util import old_col_new_col
from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts


from .col_analysis import ColAnalysis, SDType
from .analysis_management import (AnalysisPipeline, DfStats)
from buckaroo.pluggable_analysis_framework.safe_summary_df import safe_summary_df
from typing import Mapping, Any, Callable, Tuple, List, MutableMapping, Type
import warnings



class PolarsAnalysis(ColAnalysis):
    select_clauses:List[pl.Expr] = []
    column_ops: Mapping[str, Tuple[List[pl.DataType], Callable[[pl.Series], Any]]] = {}

PAObjs: TypeAlias = List[Type[PolarsAnalysis]]

def polars_select_expressions(unordered_objs: PAObjs) -> List[pl.Expr]:
    """
    Return the full list of select expressions contributed by the provided
    PolarsAnalysis classes. This mirrors the expression set used by
    polars_produce_series_df and can be used by executors to surface
    the concrete expression plan for debugging/bisecting.
    """
    exprs: List[pl.Expr] = []
    for obj in unordered_objs:
        exprs.extend(obj.select_clauses)
    return exprs

def polars_produce_series_df(df:pl.DataFrame,
                             unordered_objs:PAObjs,
                      df_name:str='test_df', debug:bool=False) -> SDType:
    """ just executes the series methods
    
    Now uses polars_series_stats_from_select_result internally to ensure
    consistency with PAFColumnExecutor.
    """
    errs: MutableMapping[str, str] = {}
    all_clauses = []
    for obj in unordered_objs:
        all_clauses.extend(obj.select_clauses)

    try:
        # First try the original approach: execute all clauses together
        result_df = df.lazy().select(all_clauses).collect()
    except Exception as e:
        if debug:
            print(f"Combined clause execution failed: {e}")
            print("Falling back to individual clause execution...")
        
        # Fallback: Execute clauses individually and combine horizontally
        try:
            individual_results = []
            for clause in all_clauses:
                try:
                    res = df.lazy().select(clause).collect()
                    individual_results.append(res)
                except Exception as clause_error:
                    if debug:
                        print(f"Skipping failed clause {clause}: {clause_error}")
                    continue
            
            # Combine results horizontally 
            if individual_results:
                try:
                    result_df = individual_results[0]
                    for additional_result in individual_results[1:]:
                        result_df = result_df.hstack(additional_result)
                    if debug:
                        print(f"Fallback successful: {result_df.shape}")
                except Exception as hstack_error:
                    # If hstack fails (e.g., height mismatches), extract values from each
                    # result separately and merge them, then reconstruct a DataFrame
                    # This matches PAFColumnExecutor behavior
                    if debug:
                        print(f"hstack failed: {hstack_error}")
                        print("Extracting values from individual results...")
                    from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts
                    from collections import defaultdict
                    import json
                    
                    merged_dict = defaultdict(dict)
                    for individual_result in individual_results:
                        result_dict = split_to_dicts(individual_result)
                        for orig_col, measures in result_dict.items():
                            merged_dict[orig_col].update(measures)
                    
                    # Reconstruct DataFrame from merged dict
                    # For value_counts, we need to preserve the Series structure
                    # For other measures, extract scalar values
                    reconstructed_cols = {}
                    for orig_col, measures in merged_dict.items():
                        for measure, value in measures.items():
                            col_name = json.dumps([orig_col, measure])
                            if measure == 'value_counts' and isinstance(value, pl.Series):
                                # Preserve the Series for value_counts (it's a Series of structs)
                                reconstructed_cols[col_name] = [value]
                            elif isinstance(value, pl.Series):
                                # For other Series, extract first element
                                scalar_val = value[0] if value.len() > 0 else None
                                reconstructed_cols[col_name] = [scalar_val]
                            elif isinstance(value, list):
                                scalar_val = value[0] if value else None
                                reconstructed_cols[col_name] = [scalar_val]
                            else:
                                reconstructed_cols[col_name] = [value]
                    
                    if reconstructed_cols:
                        result_df = pl.DataFrame(reconstructed_cols)
                    else:
                        # If no expressions worked, return error strings
                        if debug:
                            df.write_parquet('error.parq')
                        return dict([[k, str(e)] for k in df.columns]), {}
            else:
                # If no clauses worked, return error strings
                if debug:
                    df.write_parquet('error.parq')
                return dict([[k, str(e)] for k in df.columns]), {}
        except Exception as fallback_error:
            if debug:
                print(f"Fallback also failed: {fallback_error}")
                df.write_parquet('error.parq')
            return dict([[k, str(e)] for k in df.columns]), {}

    # Use polars_series_stats_from_select_result to build series stats
    # This ensures consistency with PAFColumnExecutor
    # Note: we pass run_computed_summary=False because that's done in polars_produce_summary_df
    series_stats, errs = polars_series_stats_from_select_result(
        result_df, df, unordered_objs, df_name, debug, run_computed_summary=False
    )
    
    return series_stats, errs


def polars_produce_summary_df(
    df: pl.DataFrame, series_stats: SDType,
    ordered_objs: PAObjs, df_name: str = 'test_df', debug: bool = False) -> Tuple[SDType, MutableMapping[str, str]]:
    """
    Polars-specific version of produce_summary_df that correctly handles column name mapping.
    
    The issue: polars results use original column names in JSON format like ["tripduration", "most_freq"]
    but the analysis pipeline expects rewritten names like "a", "b", "c", etc.
    """
    from .analysis_management import ColMeta, ErrDict, ColIdentifier
    
    errs: ErrDict = {}
    summary_col_dict: SDType = {}
    cols: List[ColIdentifier] = []
    cols.extend(df.columns)
    
    # Create mapping from original to rewritten column names
    orig_to_rewritten = {}
    for orig_ser_name, rewritten_col_name in old_col_new_col(df):
        orig_to_rewritten[orig_ser_name] = rewritten_col_name
    
    for orig_ser_name, rewritten_col_name in old_col_new_col(df):
        # series_stats uses rewritten column names as keys, not original names
        base_summary_dict: ColMeta = series_stats.get(rewritten_col_name, {})
        
        # Handle case where series_stats contains error strings instead of dicts
        if isinstance(base_summary_dict, str):
            base_summary_dict = {}
        
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
                    errs[(rewritten_col_name, "computed_summary")] = e, a_kls
                if debug:
                    print(f"Error in {a_kls.__name__}.computed_summary: {e}")
                continue
        summary_col_dict[rewritten_col_name] = base_summary_dict
    return summary_col_dict, errs

#FIXME shouldn't this be used by produce_summary_df?
def polars_series_stats_from_select_result(
    select_result_df: pl.DataFrame,
    original_df_for_schema: pl.DataFrame,
    unordered_objs: PAObjs,
    df_name: str = 'test_df',
    debug: bool = False,
    run_computed_summary: bool = True,
) -> SDType:
    """
    Build series-level stats given a DataFrame produced by selecting the
    analysis expressions up-front. This avoids reconstructing and executing
    those expressions here again.
    """
    errs: MutableMapping[str, str] = {}
    # Build mapping and base summary dict using only schema (no data collection needed)
    orig_col_to_rewritten: dict[str, str] = {}
    summary_dict: dict[str, dict[str, Any]] = {}
    for orig_ser_name, rewritten_col_name in old_col_new_col(original_df_for_schema):
        orig_col_to_rewritten[orig_ser_name] = rewritten_col_name
        summary_dict[rewritten_col_name] = {
            'orig_col_name': orig_ser_name,
            'rewritten_col_name': rewritten_col_name,
        }
        for a_klass in unordered_objs:
            summary_dict[rewritten_col_name].update(a_klass.provides_defaults)

    # Fill in first run dict from the provided selection results
    first_run_dict = split_to_dicts(select_result_df)
    for orig_col, measures in first_run_dict.items():
        if orig_col in orig_col_to_rewritten:
            rw_col = orig_col_to_rewritten[orig_col]
            summary_dict[rw_col].update(measures)

    # column_ops may require original series; execute them if data is available.
    # If original_df_for_schema has data (height > 0), execute column_ops similar
    # to polars_produce_series_df. If it's empty (schema-only), skip column_ops
    # for backward compatibility.
    if original_df_for_schema.height > 0:
        for pa in unordered_objs:
            for measure_name, action_tuple in pa.column_ops.items():
                col_selector, func = action_tuple
                try:
                    if col_selector == "all":
                        sub_df = original_df_for_schema.select(pl.all())
                    elif isinstance(col_selector, list):
                        # col_selector is a list of data types (e.g., NUMERIC_POLARS_DTYPES)
                        # Filter columns by matching dtype
                        matching_cols = [
                            c
                            for c in original_df_for_schema.columns
                            if original_df_for_schema[c].dtype in col_selector
                        ]
                        if not matching_cols:
                            continue
                        sub_df = original_df_for_schema.select(matching_cols)
                    else:
                        # col_selector is a column name (legacy behavior from polars_produce_series_df)
                        sub_df = original_df_for_schema.select(pl.col(col_selector))

                    for col in sub_df.columns:
                        rw_col = orig_col_to_rewritten.get(col, col)
                        if rw_col in summary_dict:
                            summary_dict[rw_col][measure_name] = func(original_df_for_schema[col])
                except Exception as e:
                    if debug:
                        print(f"Error in column_ops for {measure_name}: {e}")
                    continue

    # After base measures + column_ops, optionally run computed_summary for each analysis.
    # When run_computed_summary=False (used by polars_produce_series_df), this step is skipped
    # and computed_summary is run later in polars_produce_summary_df.
    # When run_computed_summary=True (used by PAFColumnExecutor), computed_summary runs here
    # to populate derived fields such as histogram, histogram_bins, categorical_histogram, etc.
    if run_computed_summary:
        # Note: we intentionally iterate over original_df_for_schema so that
        # old_col_new_col provides a stable mapping from original -> rewritten names.
        for orig_ser_name, rewritten_col_name in old_col_new_col(original_df_for_schema):
            base_summary_dict = summary_dict.get(rewritten_col_name, {})

            # Handle case where the entry is an error string instead of a dict
            if isinstance(base_summary_dict, str):
                base_summary_dict = {}

            for a_kls in unordered_objs:
                try:
                    if a_kls.quiet or a_kls.quiet_warnings:
                        if debug is False:
                            warnings.filterwarnings('ignore')
                        summary_res = a_kls.computed_summary(base_summary_dict)
                        warnings.filterwarnings('default')
                    else:
                        summary_res = a_kls.computed_summary(base_summary_dict)
                    base_summary_dict.update(summary_res)
                except Exception as e:
                    # Mirror behaviour of polars_produce_summary_df: record/log errors
                    # via debug prints only; callers that need structured errs should
                    # extend this function to surface them.
                    if debug:
                        print(f"Error in {a_kls.__name__}.computed_summary: {e}")
                    continue

            summary_dict[rewritten_col_name] = base_summary_dict

    return summary_dict, errs


class PolarsAnalysisPipeline(AnalysisPipeline):
    """
    manage the ordering of a set of col_analysis objects
    allow for computing summary_stats (and other oberservation sets) based on col_analysis objects
    allow col_anlysis objects to be added
    """
 
    @staticmethod
    def full_produce_summary_df(
            df:pl.DataFrame, ordered_objs:List[PolarsAnalysis],
            df_name:str='test_df', debug:bool=False):
        series_stat_dict, series_errs = polars_produce_series_df(df, ordered_objs, df_name, debug)
        
        summary_dict, summary_errs = polars_produce_summary_df(
        df, series_stat_dict, ordered_objs, df_name, debug)
        series_errs.update(summary_errs)
        return summary_dict, series_errs



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
