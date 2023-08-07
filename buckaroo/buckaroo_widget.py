#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

"""
TODO: Add module docstring
"""
import json

from ipywidgets import DOMWidget
from traitlets import Unicode, List, Dict, observe

from ._frontend import module_name, module_version
from .all_transforms import configure_buckaroo, DefaultCommandKlsList
from .summary_stats import sample

from .analysis import (TypingStats, DefaultSummaryStats, ColDisplayHints)
from .analysis_management import DfStats

from pandas.io.json import dumps as pdumps


#empty_df = pd.DataFrame({})
#json.loads(empty_df.to_json(orient='table', indent=2))
EMPTY_DF_OBJ = {'schema': {'fields': [{'name': 'index', 'type': 'string'}],
  'primaryKey': ['index'],
  'pandas_version': '1.4.0'},
 'data': []}


def dumb_table_sumarize(df):
    """used when table_hints aren't provided.  Trests every column as a string"""
    table_hints = {col:{'is_numeric':False}  for col in df}
    table_hints['index'] = {'is_numeric': False} 
    return table_hints


def df_to_obj(df, order = None, table_hints=None):
    if order is None:
        order = df.columns
    obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))
    if table_hints is None:
        obj['table_hints'] = json.loads(pdumps(dumb_table_sumarize(df)))
    else:
        obj['table_hints'] = json.loads(pdumps(table_hints))
    fields=[{'name':'index'}]
    for c in order:
        fields.append({'name':c})
    obj['schema'] = dict(fields=fields)
    return obj

FAST_SUMMARY_WHEN_GREATER = 1_000_000
class BuckarooWidget(DOMWidget):
    """TODO: Add docstring here
    """
    _model_name = Unicode('DCEFWidgetModel').tag(sync=True)
    _model_module = Unicode(module_name).tag(sync=True)
    _model_module_version = Unicode(module_version).tag(sync=True)
    _view_name = Unicode('DCEFWidgetView').tag(sync=True)
    _view_module = Unicode(module_name).tag(sync=True)
    _view_module_version = Unicode(module_version).tag(sync=True)

    commandConfig = Dict({}).tag(sync=True)
    operations = List().tag(sync=True)

    command_classes = DefaultCommandKlsList

    origDf = Dict({}).tag(sync=True)
    summaryDf = Dict({}).tag(sync=True)

    operation_results = Dict({}).tag(sync=True)

    dfConfig = Dict(
        {
        'totalRows': 1234569,
        'columns': 30,
        'rowsShown': 0,
        'sampleSize': 10_000,
        'sampled':False,
        'summaryStats': False,
        'reorderdColumns': False,
        'showTransformed': True,
        'showCommands': True,
    }).tag(sync=True)

    
    def __init__(self, df,
                 sampled=True,
                 summaryStats=False,
                 reorderdColumns=False,
                 showTransformed=True,
                 showCommands=True,
                 really_reorder_columns=False):
        super().__init__()

        rows = len(df)
        cols = len(df.columns)
        item_count = rows * cols

        fast_mode = sampled or reorderdColumns
        if item_count > FAST_SUMMARY_WHEN_GREATER:
            fast_mode = True
        elif really_reorder_columns: #an override
            fast_mode = True
        if fast_mode:
            self.dfConfig['sampled'] = True

        self.stats = DfStats(df, [TypingStats, DefaultSummaryStats, ColDisplayHints])
        self.summaryDf = df_to_obj(self.stats.presentation_sdf, self.stats.col_order)

        tempDfc = self.dfConfig.copy()
        tempDfc.update(dict(
            totalRows=len(df),
            columns=len(df.columns),
            showTransformed=showTransformed,
            showCommands=showCommands))

        self.df = df
        self.dfConfig = tempDfc
        #just called to trigger setting origDf properly
        self.update_based_on_df_config(3)
        self.operation_results = {
            'transformed_df':self.origDf,
            'generated_py_code':'#from py widget init'}
        self.setup_from_command_kls_list()

    def add_analysis(self, analysis_obj):
        self.stats.add_analysis(analysis_obj)
        self.summaryDf = df_to_obj(self.stats.presentation_sdf, self.stats.col_order)
        #just trigger redisplay
        self.update_based_on_df_config(3)

    @observe('dfConfig')
    def update_based_on_df_config(self, change):
        tdf = self.df_from_dfConfig()
        if self.dfConfig['reorderdColumns']:
            #ideally this won't require a reserialization.  All
            #possible col_orders shoudl be serialized once, and the
            #frontend should just toggle from them
            #self.origDf = df_to_obj(tdf, self.stats.col_order, table_hints=self.stats.table_hints)
            self.origDf = df_to_obj(tdf, self.stats.col_order) #, table_hints=self.stats.table_hints)
        else:
            self.origDf = df_to_obj(tdf) #, table_hints=self.stats.table_hints)

    def df_from_dfConfig(self):
        if self.dfConfig['sampled']:
            return sample(self.df, self.dfConfig['sampleSize'])
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
            #note doesn't use df_to_obj
            transformed_df = self.buckaroo_transform(operations, self.df)
            results['transformed_df'] = json.loads(transformed_df.to_json(orient='table', indent=2))
            results['transform_error'] = False

        except Exception as e:
            results['transformed_df'] = EMPTY_DF_OBJ
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

        

