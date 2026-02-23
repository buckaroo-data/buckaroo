import sys
import logging



logger = logging.getLogger()

EMPTY_DFVIEWER_CONFIG = {
    'pinned_rows': [],
    'column_config': []}
EMPTY_DF_DISPLAY_ARG = {'data_key': 'empty', 'df_viewer_config': EMPTY_DFVIEWER_CONFIG,
                           'summary_stats_key': 'empty'}



SENTINEL_COLUMN_CONFIG_1 = "ASDF"
SENTINEL_COLUMN_CONFIG_2 = "FOO-BAR"



def merge_ops(existing_ops, cleaning_ops):
    """ strip cleaning_ops from existing_ops, reinsert cleaning_ops at the beginning """
    a = existing_ops.copy()
    a.extend(cleaning_ops)
    return a

def exception_protect(protect_name=None):
    """
    used to make sure that an exception from any part of DataFlow derived classes has the minimum amount of traitlets observer stuff in the stack trace.

    Requires that a a class has `self.exception`

    protect_name occurs in the printed exception handler to narrow down the call stack
    
    """
    def wrapped_decorator(func):
        def wrapped(self, *args, **kwargs):
            try:
                func(self, *args, **kwargs)
            except Exception:
                #sometimes useful for debugging tricky call order stuff
                # if protect_name:
                #     print("protect handler", protect_name, self.exception)
                if self.exception is None:
                    self.exception = sys.exc_info()
                raise
        return wrapped
    return wrapped_decorator




class Sampling:

    max_columns      =     250
    pre_limit        = 100_000
    serialize_limit  =   5_000

    @classmethod
    def pre_stats_sample(kls, df):
        if len(df.columns) > kls.max_columns:
            print("Removing excess columns, found %d columns" %  len(df.columns))
            df = df[df.columns[:kls.max_columns]]
        if kls.pre_limit and len(df) > kls.pre_limit:
            return df.sample(kls.pre_limit)
        return df


    @classmethod
    def serialize_sample(kls, df):
        if kls.serialize_limit and len(df) > kls.serialize_limit:
            sampled = df.sample(kls.serialize_limit)
            if hasattr(sampled, 'sort_index'):
                return sampled.sort_index()
            return sampled
        return df

