#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

"""
TODO: Add module docstring
"""

from ipywidgets import DOMWidget
from traitlets import Unicode, List, Dict, observe
from ._frontend import module_name, module_version
from .all_transforms import configure_dcef, DefaultCommandKlsList
import json


class DCEFWidget(DOMWidget):
    """TODO: Add docstring here
    """
    _model_name = Unicode('DCEFWidgetModel').tag(sync=True)
    _model_module = Unicode(module_name).tag(sync=True)
    _model_module_version = Unicode(module_version).tag(sync=True)
    _view_name = Unicode('DCEFWidgetView').tag(sync=True)
    _view_module = Unicode(module_name).tag(sync=True)
    _view_module_version = Unicode(module_version).tag(sync=True)

    value = Unicode('Hello World').tag(sync=True)
    command_config = Dict({}).tag(sync=True)

    operations = List().tag(sync=True)

    command_classes = DefaultCommandKlsList

    js_df = Dict({}).tag(sync=True)

    operation_results = Dict({}).tag(sync=True)
    dfConfig = Dict(
{
        'totalRows': 5309,
        'columns': 30,
        'rowsShown': 500,
        'sampleSize': 10_000,
        'summaryStats': False,
        'reorderdColumns': False
    }).tag(sync=True)

    def __init__(self, df):
        super().__init__()
        self.df = df
        self.js_df = json.loads(df.to_json(orient='table', indent=2))
        self.operation_results = {
            'transformed_df':self.js_df,
            'generated_py_code':'#from py widget init'}
        self.setup_from_command_kls_list()

    @observe('operations')
    def interpret_operations(self, change):
        print("interpret_operations")
        try:
            operations = change['new']
            print("interpret_operations", operations)
            results = {}
            if len(operations) == 1:

                results['transformed_df'] = self.js_df
                results['generated_py_code'] = 'no operations'
                print('exiting early')
                return
            
            transformed_df = self.dcef_transform(operations, self.df)
            results['transformed_df'] = json.loads(transformed_df.to_json(orient='table', indent=2))

            results['generated_py_code'] = self.dcef_to_py_core(operations[1:])
            self.operation_results = results
            print("operations_results", results.keys())
        except Exception as e:
            print("error_setting", e)
            self.transform_error = str(e)
            raise

    def setup_from_command_kls_list(self):
        command_defaults, command_patterns, self.dcef_transform, self.dcef_to_py_core = configure_dcef(
            self.command_classes)
        self.command_config = dict(
            argspecs=command_patterns, defaultArgs=command_defaults)


    def add_command(self, incomingCommandKls):
        without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
        without_incoming.append(incomingCommandKls)
        self.command_classes = without_incoming
        self.setup_from_command_kls_list()

        
        

        
        
