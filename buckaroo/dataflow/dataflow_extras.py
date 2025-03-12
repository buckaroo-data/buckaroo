import sys
import logging


import pandas as pd
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)

logger = logging.getLogger()

EMPTY_DFVIEWER_CONFIG = {
    'pinned_rows': [],
    'column_config': []}
EMPTY_DF_DISPLAY_ARG = {'data_key': 'empty', 'df_viewer_config': EMPTY_DFVIEWER_CONFIG,
                           'summary_stats_key': 'empty'}


SENTINEL_DF_1 = pd.DataFrame({'foo'  :[10, 20], 'bar' : ["asdf", "iii"]})
SENTINEL_DF_2 = pd.DataFrame({'col1' :[55, 55], 'col2': ["pppp", "333"]})

SENTINEL_COLUMN_CONFIG_1 = "ASDF"
SENTINEL_COLUMN_CONFIG_2 = "FOO-BAR"



def merge_ops(existing_ops, cleaning_ops):
    """ strip cleaning_ops from existing_ops, reinsert cleaning_ops at the beginning """
    a = existing_ops.copy()
    a.extend(cleaning_ops)
    return a

def merge_sds(*sds):
    """merge sds with later args taking precedence

    sub-merging of "overide_config"??
    """
    base_sd = {}
    for sd in sds:
        for column in sd.keys():
            base_sd[column] = merge_column(base_sd.get(column, {}), sd[column])
    return base_sd


def merge_column(base, new):
    """
    merge individual column dictionaries, with special handling for column_config_override
    """
    ret = base.copy()
    ret.update(new)

    base_override = base.get('column_config_override', {}).copy()
    new_override = new.get('column_config_override', {}).copy()
    base_override.update(new_override)

    if len(base_override) > 0:
        ret['column_config_override'] = base_override
    return ret


def merge_column_config(styled_column_config, overide_column_configs):
    existing_column_config = styled_column_config.copy()
    ret_column_config = []
    for row in existing_column_config:
        col = row['col_name']
        if col in overide_column_configs:
            row.update(overide_column_configs[col])
        if row.get('merge_rule', 'blank') == 'hidden':
            continue
        ret_column_config.append(row)
    return ret_column_config

def style_columns(style_method:str, sd):
    if style_method == "foo":
        return SENTINEL_COLUMN_CONFIG_2
    else:
        ret_col_config = []
        for col in sd.keys():
            ret_col_config.append(
                {'col_name':col, 'displayer_args': {'displayer': 'obj'}})
        return {
            'pinned_rows': [
            #    {'primary_key_val': 'dtype', 'displayer_args': {'displayer': 'obj'}}
            ],
            'column_config': ret_col_config}


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
            sampled = df.sample(kls.pre_limit)
            if isinstance(sampled, pd.DataFrame):
                return sampled.sort_index()
            return sampled
        return df


    @classmethod
    def serialize_sample(kls, df):
        if kls.serialize_limit and len(df) > kls.serialize_limit:
            sampled = df.sample(kls.serialize_limit)
            if isinstance(sampled, pd.DataFrame):
                return sampled.sort_index()
            return sampled
        return df


class StylingAnalysis(ColAnalysis):
    provides_defaults = {}
    pinned_rows = []

    extra_grid_config = {}
    component_config = {}
    
    #the type should be
    #def style_column(col:str, column_metadata: SingleColumnMetadata) -> ColumnConfig:
    @classmethod
    def style_column(kls, col, column_metadata):
        return {'col_name':str(col), 'displayer_args': {'displayer': 'obj'}}

    #what is the key for this in the df_display_args_dictionary
    df_display_name = "main"
    data_key = "main"
    summary_stats_key= 'all_stats'

    @classmethod
    def default_styling(kls, col_name):
        return {'col_name': col_name, 'displayer_args': {'displayer': 'obj'}}

    @classmethod
    def style_columns(kls, sd):
        ret_col_config = []
        #this is necessary for polars to add an index column, which is
        #required so that summary_stats makes sense
        if 'index' not in sd:
            ret_col_config.append(kls.default_styling('index'))
            
        for col in sd.keys():
            col_meta = sd[col]
            if col_meta.get('merge_rule') == 'hidden':
                continue
            try:
                base_style = kls.style_column(col, col_meta)
            except Exception as exc:
                if len(col_meta) == 0 and len(kls.requires_summary) > 0:
                    # this is called in instantiation without col_meta, and that can cause failures
                    # we want to just swallow these errors and not warn
                    pass
                else:
                    # something unexpected happened here, warn so that the develoepr is notified
                    logger.warn(f"Warning, styling failed from {kls} on column {col} with col_meta {col_meta} using default_styling instead")
                    logger.warn(exc)
                # Always provide a style, not providing a style
                # results in no display which is a very bad user
                # experience
                base_style = kls.default_styling(col)
            if 'column_config_override' in col_meta:
                #column_config_override, sent by the instantiation, gets set later
                base_style.update(col_meta['column_config_override'])
            if base_style.get('merge_rule') == 'hidden':
                continue
            ret_col_config.append(base_style)
            
        return {
            'pinned_rows': kls.pinned_rows,
            'column_config': ret_col_config,
            'extra_grid_config': kls.extra_grid_config,
            'component_config': kls.component_config
        }

