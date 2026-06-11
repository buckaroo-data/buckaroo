from typing_extensions import TypeAlias

import polars as pl

from buckaroo.df_util import old_col_new_col
from buckaroo.pluggable_analysis_framework.polars_utils import split_to_dicts


from .col_analysis import ColAnalysis, SDType
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
    polars_series_stats_from_select_result and can be used by executors to
    surface the concrete expression plan for debugging/bisecting.
    """
    exprs: List[pl.Expr] = []
    for obj in unordered_objs:
        exprs.extend(obj.select_clauses)
    return exprs

def polars_series_stats_from_select_result(select_result_df: pl.DataFrame, original_df_for_schema: pl.DataFrame,
        unordered_objs: PAObjs, df_name: str = 'test_df', debug: bool = False, run_computed_summary: bool = True) -> SDType:
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
        summary_dict[rewritten_col_name] = {'orig_col_name': orig_ser_name, 'rewritten_col_name': rewritten_col_name}
        for a_klass in unordered_objs:
            summary_dict[rewritten_col_name].update(a_klass.provides_defaults)

    # Fill in first run dict from the provided selection results
    first_run_dict = split_to_dicts(select_result_df)
    for orig_col, measures in first_run_dict.items():
        if orig_col in orig_col_to_rewritten:
            rw_col = orig_col_to_rewritten[orig_col]
            summary_dict[rw_col].update(measures)

    # column_ops may require original series; execute them if data is available.
    # If original_df_for_schema has data (height > 0), execute column_ops.
    # If it's empty (schema-only), skip column_ops for backward compatibility.
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
                        # col_selector is a column name
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
    # When run_computed_summary=True (used by PAFColumnExecutor), computed_summary runs here
    # to populate derived fields such as histogram, histogram_bins, categorical_histogram, etc.
    # Callers that run computed_summary separately pass run_computed_summary=False.
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
                    # Errors are logged via debug prints only; callers that need
                    # structured errs should extend this function to surface them.
                    if debug:
                        print(f"Error in {a_kls.__name__}.computed_summary: {e}")
                    continue

            summary_dict[rewritten_col_name] = base_summary_dict

    return summary_dict, errs
