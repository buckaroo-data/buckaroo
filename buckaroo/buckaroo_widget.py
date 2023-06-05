#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

"""
TODO: Add module docstring
"""
import numpy as np
from ipywidgets import DOMWidget
from traitlets import Unicode, List, Dict, observe
import pandas as pd
from ._frontend import module_name, module_version
from .all_transforms import configure_buckaroo, DefaultCommandKlsList
from .summary_stats import summarize_df, reorder_columns
import json
from IPython.core.getipython import get_ipython
from IPython.display import display



def sample(df, sample_size=500, include_outliers=True):
    if len(df) <= sample_size:
        return df
    sdf = df.sample(np.min([sample_size, len(df)]))
    if include_outliers:
        outlier_idxs = []
        for col in df.columns:
            idxs = df[col].sort_values().index
            outlier_idxs.extend(idxs[:5])
            outlier_idxs.extend(idxs[-5:])
        outlier_idxs.extend(sdf.index)
        uniq_idx = np.unique(outlier_idxs)
        return df.iloc[uniq_idx]
    return sdf
            

class BuckarooWidget(DOMWidget):
    """TODO: Add docstring here
    """
    _model_name = Unicode('DCEFWidgetModel').tag(sync=True)
    _model_module = Unicode(module_name).tag(sync=True)
    _model_module_version = Unicode(module_version).tag(sync=True)
    _view_name = Unicode('DCEFWidgetView').tag(sync=True)
    _view_module = Unicode(module_name).tag(sync=True)
    _view_module_version = Unicode(module_version).tag(sync=True)

    value = Unicode('Hello World').tag(sync=True)
    commandConfig = Dict({}).tag(sync=True)

    operations = List().tag(sync=True)

    command_classes = DefaultCommandKlsList

    origDf = Dict({}).tag(sync=True)

    operation_results = Dict({}).tag(sync=True)


    dfConfig = Dict(
        {
        'totalRows': 5309,
        'columns': 30,
        'rowsShown': 500,
        'sampleSize': 10_000,
        'sampled':True,
        'summaryStats': False,
        'reorderdColumns': True,
        'showTransformed': True,
        'showCommands': True,
    }).tag(sync=True)
        
        

    # #config for the python pre-processing, waiting for inspiration for a better name
    # python_massaging = Dict({
    #     sample_threshold=20000,
    #     reorder_columns=True,
    #     max_rows=500,
    #     default_display='rows', #rows, summary, header+rows
    #     }).tag(sync=True)


    def __init__(self, df):
        super().__init__()
        self.df = df
        self.setup_dfconfig(df)
        #self.origDf = json.loads(df.to_json(orient='table', indent=2))
        self.operation_results = {
            'transformed_df':self.origDf,
            'generated_py_code':'#from py widget init'}
        self.setup_from_command_kls_list()

    #Maybe tie this to a watcher on DF?
    def setup_dfconfig(self, df):
        dfc = self.dfConfig.copy()
        dfc.update(dict(totalRows=len(df),
                        columns=len(df.columns)))
        self.dfConfig = dfc

    @observe('dfConfig')
    def update_based_on_df_config(self, change):
        old = change['old']
        new = change['new']
        tdf = self.df_from_dfConfig()
        otdf = reorder_columns(tdf)
        self.origDf = json.loads(otdf.to_json(orient='table', indent=2, default_handler=str))


    def df_from_dfConfig(self):
        if self.dfConfig['summaryStats']:
            return summarize_df(self.df)
        elif self.dfConfig['sampled']:
            return sample(self.df)
        else:
            return self.df

    @observe('operations')
    def interpret_operations(self, change):
        print("interpret_operations")
        results = {}
        results['generated_py_code'] = 'before interpreter'
        try:
            operations = [{'symbol': 'begin'}]
            operations.extend(change['new'])
            #print("interpret_operations", operations)

            if len(operations) == 1:
                results['transformed_df'] = self.origDf
                results['generated_py_code'] = 'no operations'
                #print('exiting early')
                return
            #generating python code seems slightly less error prone than the transform
            results['generated_py_code'] = self.buckaroo_to_py_core(operations[1:])            
            transformed_df = self.buckaroo_transform(operations, self.df)
            results['transformed_df'] = json.loads(transformed_df.to_json(orient='table', indent=2))
            results['transform_error'] = False

        except Exception as e:
            empty_df = pd.DataFrame({})
            results['transformed_df'] = json.loads(empty_df.to_json(orient='table', indent=2))
            print(e)
            results['transform_error'] = str(e)
        self.operation_results = results

    def setup_from_command_kls_list(self):
        command_defaults, command_patterns, self.buckaroo_transform, self.buckaroo_to_py_core = configure_buckaroo(
            self.command_classes)
        self.commandConfig = dict(
            argspecs=command_patterns, defaultArgs=command_defaults)


    def add_command(self, incomingCommandKls):
        without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
        without_incoming.append(incomingCommandKls)
        self.command_classes = without_incoming
        self.setup_from_command_kls_list()

def _display_as_buckaroo(df):
    return display(BuckarooWidget(df))

def enable():
    """
    Automatically use buckaroo to display all DataFrames
    instances in the notebook.

    """
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        raise ImportError('This feature requires IPython 1.0+')

    ip = get_ipython()
    ip_formatter = ip.display_formatter.ipython_display_formatter

    ip_formatter.for_type(pd.DataFrame, _display_as_buckaroo)
    
enable()

def disable():
    """
    Automatically use buckaroo to display all DataFrames
    instances in the notebook.

    """
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        raise ImportError('This feature requires IPython 1.0+')

    ip = get_ipython()
    ip_formatter = ip.display_formatter.ipython_display_formatter
    ip_formatter.type_printers.pop(pd.DataFrame, None)    
