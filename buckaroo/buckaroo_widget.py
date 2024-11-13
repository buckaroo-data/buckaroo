#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

"""
TODO: Add module docstring
"""

import traceback
from ipywidgets import DOMWidget
import json
import pandas as pd
from traitlets import Unicode, List, Dict, observe

from ._frontend import module_name, module_version


from .customizations.analysis import (TypingStats, ComputedDefaultSummaryStats, DefaultSummaryStats)
from .customizations.histogram import (Histogram)
from .customizations.pd_autoclean_conf import (CleaningConf, NoCleaningConf)
from .customizations.styling import (DefaultSummaryStatsStyling, DefaultMainStyling)
from .pluggable_analysis_framework.analysis_management import DfStats
from .pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis

from .serialization_utils import EMPTY_DF_WHOLE, check_and_fix_df, pd_to_obj
from .dataflow.dataflow import CustomizableDataflow, StylingAnalysis
from .dataflow.dataflow_extras import (Sampling, exception_protect, merge_column_config)
from .dataflow.autocleaning import PandasAutocleaning


class BuckarooProjectWidget(DOMWidget):
    """
    Repetitious code needed to make Jupyter communicate properly with any BuckarooWidget in this package
    
    """
    _model_module = Unicode(module_name).tag(sync=True)
    _view_module  = Unicode(module_name).tag(sync=True)

    _model_module_version = Unicode(module_version).tag(sync=True)
    _view_module_version  = Unicode(module_version).tag(sync=True)



class PdSampling(Sampling):
    @classmethod
    def pre_stats_sample(kls, df):
        # this is a bad place for fixing the dataframe, but for now
        # it's expedient. There probably should be a nother processing
        # step
        df = check_and_fix_df(df)
        if len(df.columns) > kls.max_columns:
            print("Removing excess columns, found %d columns" %  len(df.columns))
            df = df[df.columns[:kls.max_columns]]
        if kls.pre_limit and len(df) > kls.pre_limit:
            sampled = df.sample(kls.pre_limit)
            if isinstance(sampled, pd.DataFrame):
                return sampled.sort_index()
            return sampled
        return df
    pre_limit = 1_000_000


def sym(name):
    return {'symbol':name}

symDf = SymbolDf = {'symbol': 'df'}
class BuckarooWidget(CustomizableDataflow, BuckarooProjectWidget):
    """Extends CustomizableDataFlow and DOMWIdget

    Replaces generic options in CustomizableDataFlow with Pandas implementations
    Also adds buckaroo_state object and communication to simpler CustomizableDataFlow implementations
    
    """

    #### DOMWidget Boilerplate
    _model_name = Unicode('DCEFWidgetModel').tag(sync=True)
    _view_name = Unicode('DCEFWidgetView').tag(sync=True)
    #END DOMWidget Boilerplate

    sampling_klass = PdSampling
    autocleaning_klass = PandasAutocleaning #override the base CustomizableDataFlow klass
    DFStatsClass = DfStats # Pandas Specific
    autoclean_conf = tuple([CleaningConf, NoCleaningConf]) #override the base CustomizableDataFlow conf

    operation_results = Dict(
        {'transformed_df': EMPTY_DF_WHOLE, 'generated_py_code':'# instantiation, unused'}
    ).tag(sync=True)

    df_meta = Dict({
        'columns': 5, # dummy data
        'rows_shown': 20,
        'total_rows': 877}).tag(sync=True)


    buckaroo_state = Dict({
        'cleaning_method': 'NoCleaning',
        'post_processing': '',
        'sampled': False,
        'show_commands': False,
        'df_display': 'main',
        'search_string': '',
        'quick_command_args': {}
    }).tag(sync=True)

    def to_dfviewer_ex(self):
        df_data_json = json.dumps(self.df_data_dict['main'], indent=4)
        summary_stats_data_json = json.dumps(self.df_data_dict['all_stats'], indent=4)
        df_config_json = json.dumps(self.df_display_args['main']['df_viewer_config'], indent=4)
        code_str = f"""
import React, {{useState}} from 'react';
import {{extraComponents}} from 'buckaroo';


export const df_data = {df_data_json}

export const summary_stats_data = {summary_stats_data_json}

export const dfv_config = {df_config_json}
        
export default function DFViewerExString() {{

    const [activeCol, setActiveCol] = useState('tripduration');
    return (
        <extraComponents.DFViewer
        df_data={{df_data}}
        df_viewer_config={{dfv_config}}
        summary_stats_data={{summary_stats_data}}
        activeCol={{activeCol}}
        setActiveCol={{setActiveCol}}
            />
    );
}}
"""
        return code_str

    def to_widgetdcfecell_ex(self):
        code_str = f"""
import React, {{useState}} from 'react';
import {{extraComponents}} from 'buckaroo';

const df_meta = {json.dumps(self.df_meta, indent=4)}

const df_display_args = {json.dumps(self.df_display_args, indent=4)}

const df_data_dict = {json.dumps(self.df_data_dict, indent=4)}

const buckaroo_options = {json.dumps(self.buckaroo_options, indent=4)}

const buckaroo_state = {json.dumps(self.buckaroo_state, indent=4)}

const commandConfig = {json.dumps(self.commandConfig, indent=4)}

const w_operations = {json.dumps(self.operations, indent=4)}

const operation_results = {json.dumps(self.operation_results, indent=4)}
        
export default function  WidgetDCFCellExample() {{
     const [bState, setBState] = React.useState<BuckarooState>(buckaroo_state);
    const [operations, setOperations] = useState<Operation[]>(w_operations);
    return (
        <extraComponents.WidgetDCFCell
            df_meta={{df_meta}}
            df_display_args={{df_display_args}}
            df_data_dict={{df_data_dict}}
            buckaroo_options={{buckaroo_options}}
            buckaroo_state={{bState}}
            on_buckaroo_state={{setBState}}
            commandConfig={{commandConfig}}
            operations={{operations}}
            on_operations={{setOperations}}
            operation_results={{operation_results}}
        />
    );
}}

"""
        return code_str



    @observe('buckaroo_state')
    @exception_protect('buckaroo_state-protector')
    def _buckaroo_state(self, change):
        #how to control ordering of column_config???
        # dfviewer_config = self._get_dfviewer_config(self.merged_sd, self.style_method)
        # self.widget_args_tuple = [self.processed_df, self.merged_sd, dfviewer_config]
        old, new = change['old'], change['new']
        if not old['post_processing'] == new['post_processing']: 
            self.post_processing_method = new['post_processing']
        if not old['quick_command_args'] == new['quick_command_args']: 
            self.quick_command_args = new['quick_command_args']


        
    #widget config.  Change these via inheritance to alter core behaviors of buckaroo
    #command_klasses = DefaultCommandKlsList
    analysis_klasses = [TypingStats, DefaultSummaryStats,
                        Histogram,
                        ComputedDefaultSummaryStats,
                        StylingAnalysis,
                        DefaultSummaryStats,
                        DefaultSummaryStatsStyling, DefaultMainStyling]



    def add_analysis(self, analysis_klass):
        """
        same as get_summary_sd, call whatever to set summary_sd and trigger further comps
        """

        stats = self.DFStatsClass(
            self.processed_df,
            self.analysis_klasses,
            self.df_name, debug=self.debug)
        stats.add_analysis(analysis_klass)
        self.analysis_klasses = stats.ap.ordered_a_objs
        self.setup_options_from_analysis()
        self.summary_sd = stats.sdf

    def add_processing(self, df_processing_func):
        proc_func_name = df_processing_func.__name__
        class DecoratedProcessing(ColAnalysis):
            provides_defaults = {}
            @classmethod
            def post_process_df(kls, df):
                new_df = df_processing_func(df)
                return [new_df, {}]
            post_processing_method = proc_func_name
        self.add_analysis(DecoratedProcessing)
        temp_buckaroo_state = self.buckaroo_state.copy()
        temp_buckaroo_state['post_processing'] = proc_func_name
        self.buckaroo_state = temp_buckaroo_state


class RawDFViewerWidget(BuckarooProjectWidget):
    """

    A very raw way of instaniating just the DFViewer, not meant for use by enduers

    instead use DFViewer, or PolarsDFViewer which have better convience methods
    """

    #### DOMWidget Boilerplate
    # _model_name = Unicode('InfiniteViewerModel').tag(sync=True)
    # _view_name = Unicode('InfiniteViewerView').tag(sync=True)
    _model_name = Unicode('DFViewerModel').tag(sync=True)
    _view_name = Unicode('DFViewerView').tag(sync=True)
    #_model_id =  Unicode('paddy').tag(sync=True)
    #END DOMWidget Boilerplate

    df_data = List([
        {'a':  5  , 'b':20, 'c': 'Paddy'},
        {'a': 58.2, 'b': 9, 'c': 'Margaret'}]).tag(sync=True)

    df_viewer_config = Dict({
        'column_config': [
            { 'col_name': 'a',
              'displayer_args': { 'displayer': 'float',   'min_fraction_digits': 2, 'max_fraction_digits': 8 }},
            { 'col_name': 'b',
              'displayer_args': { 'displayer': 'integer', 'min_digits': 3, 'max_digits': 5 }},
            { 'col_name': 'c',
              'displayer_args': { 'displayer': 'string',  'min_digits': 3, 'max_digits': 5 }}],
        'pinned_rows': [
            { 'primary_key_val': 'dtype', 'displayer_args': { 'displayer': 'obj' }},
            { 'primary_key_val': 'mean', 'displayer_args': { 'displayer': 'integer', 'min_digits': 3, 'max_digits': 5 }}]}
                            ).tag(sync=True)

    summary_stats_data = List([
        { 'index': 'mean',  'a':      28,   'b':      14, 'c': 'Padarget' },
        { 'index': 'dtype', 'a': 'float64', 'b': 'int64', 'c': 'object' }]).tag(sync=True)

"""
interface PayloadArgs {
    sourceName: string;
    start: number;
    end: number
}
interface PayloadResponse {
    key: PayloadArgs;
    data: DFData;
}
"""

class InfiniteViewerWidget(BuckarooProjectWidget):
    """

    A very raw way of instaniating just the DFViewer, not meant for use by enduers

    instead use DFViewer, or PolarsDFViewer which have better convience methods
    """

    #### DOMWidget Boilerplate
    # _model_name = Unicode('InfiniteViewerModel').tag(sync=True)
    # _view_name = Unicode('InfiniteViewerView').tag(sync=True)
    _model_name = Unicode('InfiniteViewerModel').tag(sync=True)
    _view_name = Unicode('InfiniteViewerView').tag(sync=True)
    #END DOMWidget Boilerplate


    def __init__(self, df):
        super().__init__()
        print("InfiniteViewerWidget 231")
        self.df = df

    payloadArgs = Dict({'sourceName':'[]', 'start':0, 'end':50}).tag(sync=True)
    payloadResponse = Dict({'key': {'sourceName':'[]', 'start':0, 'end':49},
                            'data': []}
                            ).tag(sync=True)

    #    @exception_protect('payloadArgsHandler')    
    @observe('payloadArgs')
    def _payloadArgsHandler(self, change):
        start, end = self.payloadArgs['start'], self.payloadArgs['end']
        print(self.payloadArgs)
        if self.payloadArgs.get('sort'):
            sort_dir = self.payloadArgs.get('sort_direction')
            ascending = sort_dir == 'asc'
            slice_df = pd_to_obj(self.df.sort_values(by=[self.payloadArgs.get('sort')], ascending=ascending)[start:end])
        else:
            slice_df = pd_to_obj(self.df[start:end])
        self.payloadResponse = {'key':self.payloadArgs, 'data':slice_df}



class InfinitePdSampling(PdSampling):
    serialize_limit = -1 #this turns off rows shown in the UI
    
class BuckarooInfiniteWidget(BuckarooWidget):
    """Extends CustomizableDataFlow and DOMWIdget

    Replaces generic options in CustomizableDataFlow with Pandas implementations
    Also adds buckaroo_state object and communication to simpler CustomizableDataFlow implementations
    
    """

    #### DOMWidget Boilerplate
    _model_name = Unicode('BuckarooInfiniteWidgetModel').tag(sync=True)
    _view_name =  Unicode('BuckarooInfiniteWidgetView').tag(sync=True)
    #END DOMWidget Boilerplate

    sampling_klass = InfinitePdSampling
    #final processing block
    @observe('widget_args_tuple')
    def _handle_widget_change(self, change):
        """
       put together df_dict for consumption by the frontend
        """
        _unused, processed_df, merged_sd = self.widget_args_tuple
        if processed_df is None:
            return

        # df_data_dict is still hardcoded for now
        # eventually processed_df will be able to add or alter values of df_data_dict
        # correlation would be added, filtered would probably be altered

        # to expedite processing maybe future provided dfs from
        # postprcoessing could default to empty until that is
        # selected, optionally
        
        #note this needs to be empty so that we can do the infinite stuff
        self.df_data_dict = {'main': [],
                             'all_stats': self._sd_to_jsondf(merged_sd),
                             'empty': []}

        temp_display_args = {}
        for display_name, A_Klass in self.df_display_klasses.items():
            df_viewer_config = A_Klass.style_columns(merged_sd)
            base_column_config = df_viewer_config['column_config']
            df_viewer_config['column_config'] =  merge_column_config(
                base_column_config, self.column_config_overrides)
            disp_arg = {'data_key': A_Klass.data_key,
                        #'df_viewer_config': json.loads(json.dumps(df_viewer_config)),
                        'df_viewer_config': df_viewer_config,
                        'summary_stats_key': A_Klass.summary_stats_key}
            temp_display_args[display_name] = disp_arg

        if self.pinned_rows is not None:
            temp_display_args['main']['df_viewer_config']['pinned_rows'] = self.pinned_rows
        if self.extra_grid_config:
            temp_display_args['main']['df_viewer_config']['extra_grid_config'] = self.extra_grid_config
        if self.component_config:
            temp_display_args['main']['df_viewer_config']['component_config'] = self.component_config

        self.df_display_args = temp_display_args

    payload_args = Dict({'sourceName':'unused', 'start':0, 'end':50}).tag(sync=True)
    payload_response = Dict({'key': {'sourceName':'unused', 'start':0, 'end':49},
                            'data': []}
                            ).tag(sync=True)

    #    @exception_protect('payloadArgsHandler')    
    @observe('payload_args')
    def _payload_args_handler(self, change):

        start, end = self.payload_args['start'], self.payload_args['end']
        print("payload_args changed", start, end)
        _unused, processed_df, merged_sd = self.widget_args_tuple
        if processed_df is None:
            return

        print(self.payload_args)
        try:
            if self.payload_args.get('sort'):
                sort_dir = self.payload_args.get('sort_direction')
                ascending = sort_dir == 'asc'
                sorted_df = processed_df.sort_values(by=[self.payload_args.get('sort')], ascending=ascending)
                slice_df = pd_to_obj(sorted_df[start:end])
                self.payload_response = {'key':self.payload_args, 'data':slice_df, 'length':len(sorted_df)}
            else:
                slice_df = pd_to_obj(processed_df[start:end])
                self.payload_response = {'key':self.payload_args, 'data':slice_df, 'length':len(processed_df)}
        except Exception as e:
            print(e)
            stack_trace = traceback.format_exc()
            self.payload_response = {'key':self.payload_args, 'data':[], 'error_info':stack_trace, 'length':0}
            raise

    def _df_to_obj(self, df:pd.DataFrame):
        return pd_to_obj(df)

