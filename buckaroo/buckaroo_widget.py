#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

"""
TODO: Add module docstring
"""
import json
import warnings

from ipywidgets import DOMWidget
from traitlets import Unicode, List, Dict, observe

from ._frontend import module_name, module_version
from .all_transforms import configure_buckaroo, DefaultCommandKlsList
from .lisp_utils import (lists_match, split_operations)

from .auto_clean import get_auto_type_operations
from .down_sample import sample

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
    machine_gen_operations = List().tag(sync=True)
    command_classes = DefaultCommandKlsList

    origDf = Dict({}).tag(sync=True)
    summaryDf = Dict({}).tag(sync=True)

    operation_results = Dict(
        {'transformed_df':EMPTY_DF_OBJ, 'generated_py_code':'# instantiation, unused'}
    ).tag(sync=True)

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


    def should_sample(self, df, sampled, reorderdColumns):
        rows = len(df)
        cols = len(df.columns)
        item_count = rows * cols
        fast_mode = sampled or reorderdColumns
        if item_count > FAST_SUMMARY_WHEN_GREATER:
            fast_mode = True
        if fast_mode:
            return True
        return False

    def get_df_config(self, df, sampled, reorderdColumns, showCommands):
        tempDfc = self.dfConfig.copy()
        tempDfc.update(dict(
            totalRows=len(df),
            columns=len(df.columns),
            #removing showCommands for now, mirroring showTransformed
            showCommands=showCommands))
        tempDfc['sampled'] = self.should_sample(df, sampled, reorderdColumns)
        return tempDfc
    
    def __init__(self, df,
                 sampled=True,
                 summaryStats=False,
                 reorderdColumns=False,
                 showCommands=True):
        super().__init__()
        warnings.filterwarnings('ignore')
        #moving setup_from_command_kls_list early in the init because
        #it's relatively benign and not tied to other linked updates

        self.setup_from_command_kls_list()
        self.dfConfig = self.get_df_config(df, sampled, reorderdColumns, showCommands)
        #we need dfConfig setup first before we get the proper
        #working_df  and generate the typed_df
        self.raw_df = df

        # this will trigger the setting of self.typed_df
        self.operations = get_auto_type_operations(df)
        warnings.filterwarnings('default')

    @observe('dfConfig')
    def update_based_on_df_config(self, change):
        if hasattr(self, 'typed_df'):
            self.origDf = df_to_obj(self.typed_df, self.typed_df.columns, table_hints=self.stats.table_hints)
        #otherwise this is a call before typed_df has been completely setup

    @observe('operations')
    def handle_operations(self, change):
        if lists_match(change['old'], change['new']):
            return
        new_ops = change['new']
        split_ops = split_operations(new_ops)
        self.machine_gen_operations = split_ops[0]
        
        user_gen_ops = split_ops[1]

        #if either the user_gen part or the machine_gen part changes,
        #we still have to recompute the generated code and
        #resulting_df because the input df will be different

        results = {}
        try:
            transformed_df = self.interpret_ops(user_gen_ops, self.typed_df)
            #note we call gneerate_py_code based on the full
            #self.operations, this makes sure that machine_gen
            #cleaning code shows up too
            results['generated_py_code'] = self.generate_code(new_ops)
            results['transformed_df'] = json.loads(transformed_df.to_json(orient='table', indent=2))
            results['transform_error'] = False
        except Exception as e:
            results['transformed_df'] = EMPTY_DF_OBJ
            print(e)
            results['transform_error'] = str(e)
        self.operation_results = results

    @observe('machine_gen_operations')
    def interpret_machine_gen_ops(self, change, force=False):
        if (not force) and lists_match(change['old'], change['new']):
            return # nothing changed, do no computations
        new_ops = change['new']
        
        #this won't listen to sampled changes proeprly
        if self.dfConfig['sampled']:
            working_df = sample(self.raw_df, self.dfConfig['sampleSize'])
        else:
            working_df = self.raw_df
        self.typed_df = self.interpret_ops(new_ops, working_df)

        # stats need to be rerun each time 
        self.stats = DfStats(self.typed_df, [TypingStats, DefaultSummaryStats, ColDisplayHints])
        self.summaryDf = df_to_obj(self.stats.presentation_sdf, self.stats.col_order)
        self.update_based_on_df_config(3)

    def generate_code(self, operations):
        if len(operations) == 0:
            return 'no operations'
        return self.buckaroo_to_py_core(operations)
    
    def interpret_ops(self, new_ops, df):
        operations = [{'symbol': 'begin'}]
        operations.extend(new_ops)
        if len(operations) == 1:
            return df
        return self.buckaroo_transform(operations , df)

    def setup_from_command_kls_list(self):
        #used to initially setup the interpreter, and when a command
        #is added interactively
        command_defaults, command_patterns, self.buckaroo_transform, self.buckaroo_to_py_core = configure_buckaroo(
            self.command_classes)
        self.commandConfig = dict(argspecs=command_patterns, defaultArgs=command_defaults)


    def add_command(self, incomingCommandKls):
        without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
        without_incoming.append(incomingCommandKls)
        self.command_classes = without_incoming
        self.setup_from_command_kls_list()

    def add_analysis(self, analysis_obj):
        self.stats.add_analysis(analysis_obj)
        self.summaryDf = df_to_obj(self.stats.presentation_sdf, self.stats.col_order)
        #just trigger redisplay
        self.update_based_on_df_config(3)

        
class Unused():
    def update_based_on_df_config(self, change):

        if self.dfConfig['reorderdColumns']:
            #ideally this won't require a reserialization.  All
            #possible col_orders shoudl be serialized once, and the
            #frontend should just toggle from them
            #self.origDf = df_to_obj(tdf, self.stats.col_order, table_hints=self.stats.table_hints)
            self.origDf = df_to_obj(self.typed_df, self.stats.col_order, table_hints=self.stats.table_hints)
        else:
            self.origDf = df_to_obj(tdf, tdf.columns, table_hints=self.stats.table_hints)
