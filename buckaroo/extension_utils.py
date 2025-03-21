import pandas as pd
import buckaroo
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis


def hide_orig_columns(orig_df, new_df):
    """
    convience method used for post_processing_functions that change the shape/name of columns,
    provides a summary_dict that removes all columns from the orig_df that don't occur in new_df
    """
    remove_columns = orig_df.columns.difference(new_df.columns)
    return {k: {'merge_rule': 'hidden'} for k in remove_columns}

def get_analysis_class(summary_name, summary_df):
    # This works better as a function returning a class.
    class AnonymousClass(ColAnalysis):
        @classmethod
        def post_process_df(kls, df):
            extra_sdf = hide_orig_columns(df, summary_df)
            return [summary_df, extra_sdf]
        post_processing_method = summary_name
    return AnonymousClass


#returns a subclass of BuckarooWidget
def get_baked_post_processing_buckaroo(df_dict:dict[str, pd.DataFrame]):
    post_processing_classes = buckaroo.BuckarooWidget.analysis_klasses.copy()

    for summary_name, summary_df in df_dict.items():
        post_processing_classes.append(get_analysis_class(summary_name, summary_df))
        
    class BuckarooAnonymous(buckaroo.BuckarooWidget):
        analysis_klasses=post_processing_classes
    return BuckarooAnonymous
