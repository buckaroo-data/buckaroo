#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Paddy Mullen.
# Distributed under the terms of the Modified BSD License.

"""
TODO: Add module docstring
"""
import traceback
from typing import Literal, Union
import pandas as pd
import json
import logging
import random
import string

from traitlets import List, Dict, observe, Unicode, Any, Bool
import anywidget

from .customizations.analysis import (TypingStats, ComputedDefaultSummaryStats, DefaultSummaryStats)
from .customizations.histogram import (Histogram)
from .customizations.pd_autoclean_conf import (CleaningConf, NoCleaningConf, AggressiveAC, ConservativeAC)
from .customizations.styling import (DefaultSummaryStatsStyling, DefaultMainStyling, CleaningDetailStyling)
from .pluggable_analysis_framework.analysis_management import DfStats
from .pluggable_analysis_framework.col_analysis import ColAnalysis
from buckaroo.extension_utils import copy_extend

from .serialization_utils import EMPTY_DF_WHOLE, check_and_fix_df, pd_to_obj, to_parquet
from .dataflow.dataflow import CustomizableDataflow
from .dataflow.dataflow_extras import (Sampling, exception_protect)
from .dataflow.styling_core import (ComponentConfig, DFViewerConfig, DisplayArgs, OverrideColumnConfig, PinnedRowConfig, StylingAnalysis, merge_column_config, EMPTY_DFVIEWER_CONFIG)
from .dataflow.autocleaning import PandasAutocleaning
from pathlib import Path

logger = logging.getLogger()

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


symDf = SymbolDf = {'symbol': 'df'}


def wire_change_to_inner(outer_instance, inner_instance, prop_name):
    def propagate_change(change):
        outer_val, inner_val = getattr(outer_instance, prop_name), getattr(inner_instance, prop_name)
        if outer_val == inner_val:
            #prevent loops
            return
        setattr(inner_instance, prop_name, getattr(outer_instance, prop_name))
    outer_instance.observe(propagate_change, prop_name)

def bidirectional_wire(outer_instance, inner_instance, prop_name):
    wire_change_to_inner(outer_instance, inner_instance, prop_name)
    wire_change_to_inner(inner_instance, outer_instance, prop_name)
    outer_val, inner_val = getattr(outer_instance, prop_name), getattr(inner_instance, prop_name)
    if not inner_val == outer_val:
        setattr(outer_instance, prop_name, inner_val)

    
class BuckarooWidgetBase(anywidget.AnyWidget):
    """Extends CustomizableDataFlow and DOMWIdget

    Replaces generic options in CustomizableDataFlow with Pandas implementations
    Also adds buckaroo_state object and communication to simpler CustomizableDataFlow implementations
    
    """
    record_transcript = Bool(False).tag(sync=True)


    def get_story_config(self, include_summary_stats=False, test_name=None) -> str:
        df = self.dataflow.processed_df
        if len(df) > 100 or len(df.columns) > 20:
            raise Exception("This dataframe or columns is pretty big, you don't want to serialize it")
        args_dict = {'args':
             {'data': pd_to_obj(self.dataflow.processed_df),
            'df_viewer_config': self.dataflow.df_display_args[self.buckaroo_state['df_display']]['df_viewer_config'],
            'secondary_df_viewer_config': EMPTY_DFVIEWER_CONFIG}}
        args_dict['args']['summary_stats_data'] = []
        if include_summary_stats:
            1/0 # not supported yet
            # summary_stats data is big, and most of the time you won't want to serialize it
            #args_dict['summary_stats_data'] = {} #desrialize here

        test_name = test_name or ''.join(random.choices(string.ascii_letters, k=8))
        args_json_str = json.dumps(args_dict, indent=4)
        code_str = f"export const {test_name} :Story = {args_json_str}"
        return code_str
        

    def __init__(self, orig_df, debug=False,
        column_config_overrides:Union[Literal[None], OverrideColumnConfig]=None,
        pinned_rows:Union[Literal[None], PinnedRowConfig]=None, extra_grid_config=None,
        component_config:Union[Literal[None], ComponentConfig]=None,
        init_sd=None, skip_main_serial=False, record_transcript=False):
        """
        BuckarooWidget was originally designed to extend CustomizableDataFlow

        Because I want to more tightly control which traits are serialized to the frontend
        I have now split them

        Previously the entire dataframe would be synced to the frontend

        this is slow, and it broke marimo

        """
        super().__init__()
        self.record_transcript = record_transcript
        self.exception = None
        kls = self.__class__
        class InnerDataFlow(CustomizableDataflow):
            sampling_klass = kls.sampling_klass
            autocleaning_klass = kls.autocleaning_klass
            DFStatsClass = kls.DFStatsClass
            autoclean_conf= kls.autoclean_conf
            analysis_klasses = kls.analysis_klasses

            def _df_to_obj(idfself, df:pd.DataFrame):
                return self._df_to_obj(df)

        self.dataflow = InnerDataFlow(
            orig_df,
            debug=debug,column_config_overrides=column_config_overrides,
            pinned_rows=pinned_rows, extra_grid_config=extra_grid_config,
            component_config=component_config, init_sd=init_sd,
            skip_main_serial=skip_main_serial)

        bidirectional_wire(self, self.dataflow, "df_data_dict")
        bidirectional_wire(self, self.dataflow, "df_display_args")
        bidirectional_wire(self, self.dataflow, "df_meta")

        bidirectional_wire(self, self.dataflow, "operations")
        bidirectional_wire(self, self.dataflow, "operation_results")
        bidirectional_wire(self, self.dataflow, "buckaroo_options")
        bidirectional_wire(self, self.dataflow, "command_config")
        
    def _df_to_obj(self, df:pd.DataFrame):
        return pd_to_obj(self.sampling_klass.serialize_sample(df))


    _esm = Path(__file__).parent / "static" / "widget.js"
    _css = Path(__file__).parent / "static" / "compiled.css"

    #used for selecting the right codepath in the widget.tsx since we
    #can only have a single exported function with anywidget
    render_func_name = Unicode("baked").tag(sync=True)


    sampling_klass = PdSampling
    autocleaning_klass = PandasAutocleaning #override the base CustomizableDataFlow klass
    DFStatsClass = DfStats # Pandas Specific
    autoclean_conf = tuple([CleaningConf, NoCleaningConf]) #override the base CustomizableDataFlow conf


    df_data_dict = Dict({}).tag(sync=True)
    df_display_args: DisplayArgs = Dict({}).tag(sync=True)
    #information about the dataframe
    df_meta = Dict({
        'columns': 5, # dummy data
        'rows_shown': 20,
        'total_rows': 877}).tag(sync=True)

    operations = Any([]).tag(sync=True)
    operation_results = Dict(
        {'transformed_df': EMPTY_DF_WHOLE, 'generated_py_code':'# instantiation, unused'}
    ).tag(sync=True)
    command_config = Dict({}).tag(sync=True)

    buckaroo_options = Dict({}).tag(sync=True)


    
    #information about the current configuration of buckaroo
    buckaroo_state = Dict({
        'cleaning_method': '',
        'post_processing': '',
        'sampled': False,
        'show_commands': False,
        'df_display': 'main',
        'search_string': '',
        'quick_command_args': {}
    }).tag(sync=True)


    @observe('buckaroo_state')
    @exception_protect('buckaroo_state-protector')
    def _buckaroo_state(self, change):
        old, new = change['old'], change['new']
        if not old['post_processing'] == new['post_processing']:
            self.dataflow.post_processing_method = new['post_processing']
        if not old['cleaning_method'] == new['cleaning_method']:
            self.dataflow.cleaning_method = new['cleaning_method']
        if not old['quick_command_args'] == new['quick_command_args']:
            self.dataflow.quick_command_args = new['quick_command_args']

        
    #widget config.  Change these via inheritance to alter core behaviors of buckaroo
    #command_klasses = DefaultCommandKlsList
    analysis_klasses = [TypingStats, DefaultSummaryStats,
                        Histogram,
                        ComputedDefaultSummaryStats,
                        StylingAnalysis,
                        DefaultSummaryStats,
                        DefaultSummaryStatsStyling, DefaultMainStyling]


    def add_analysis(self, analysis_klass):
        self.dataflow.add_analysis(analysis_klass)

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

    def _sd_to_jsondf(self, sd):
        """exists so this can be overriden for polars  """
        temp_sd = sd.copy()
        return self._df_to_obj(pd.DataFrame(temp_sd))



class BuckarooWidget(BuckarooWidgetBase):
    render_func_name = Unicode("BuckarooWidget").tag(sync=True)


class RawDFViewerWidget(BuckarooWidgetBase):
    """

    A very raw way of instaniating just the DFViewer, not meant for use by enduers

    instead use DFViewer, or PolarsDFViewer which have better convience methods
    """
    render_func_name = Unicode("DFViewer").tag(sync=True)
    df_data = List([
        {'a':  5  , 'b':20, 'c': 'Paddy'},
        {'a': 58.2, 'b': 9, 'c': 'Margaret'}]).tag(sync=True)

    df_viewer_config: DFViewerConfig = Dict({
        'column_config': [],
        'pinned_rows': [],
        'first_col_configs':[]}).tag(sync=True)


    summary_stats_data = List([
        { 'index': 'mean',  'a':      28,   'b':      14, 'c': 'Padarget' },
        { 'index': 'dtype', 'a': 'float64', 'b': 'int64', 'c': 'object' }]).tag(sync=True)

    def __init__(self, df_data=None, df_viewer_config=None, summary_stats_data=None, **kwargs):
        """Initialize RawDFViewerWidget with pre-computed data.
        
        This bypasses the normal BuckarooWidgetBase initialization which requires orig_df.
        Instead, it accepts pre-computed df_data, df_viewer_config, and summary_stats_data.
        """
        # Call anywidget.AnyWidget.__init__ directly, bypassing BuckarooWidgetBase.__init__
        super(BuckarooWidgetBase, self).__init__(**kwargs)
        if df_data is not None:
            self.df_data = df_data
        if df_viewer_config is not None:
            self.df_viewer_config = df_viewer_config
        if summary_stats_data is not None:
            self.summary_stats_data = summary_stats_data

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


class InfinitePdSampling(PdSampling):
    serialize_limit = -1 #this turns off rows shown in the UI
    
class BuckarooInfiniteWidget(BuckarooWidget):
    """Extends CustomizableDataFlow and DOMWIdget

    Replaces generic options in CustomizableDataFlow with Pandas implementations
    Also adds buckaroo_state object and communication to simpler CustomizableDataFlow implementations
    
    """
        


    render_func_name = Unicode("BuckarooInfiniteWidget").tag(sync=True)    
    sampling_klass = InfinitePdSampling
    #final processing block
    def _handle_widget_change(self, change):
        """
       put together df_dict for consumption by the frontend
        """
        _unused, processed_df, merged_sd = self.dataflow.widget_args_tuple
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
        for display_name, A_Klass in self.dataflow.df_display_klasses.items():
            df_viewer_config = A_Klass.get_dfviewer_config(merged_sd, processed_df)
            base_column_config = df_viewer_config['column_config']
            df_viewer_config['column_config'] =  merge_column_config(
                base_column_config, self.dataflow.processed_df, self.dataflow.column_config_overrides)
            disp_arg = {'data_key': A_Klass.data_key,
                        #'df_viewer_config': json.loads(json.dumps(df_viewer_config)),
                        'df_viewer_config': df_viewer_config,
                        'summary_stats_key': A_Klass.summary_stats_key}
            temp_display_args[display_name] = disp_arg

        if self.dataflow.pinned_rows is not None:
            temp_display_args['main']['df_viewer_config']['pinned_rows'] = self.dataflow.pinned_rows
        if self.dataflow.extra_grid_config:
            temp_display_args['main']['df_viewer_config']['extra_grid_config'] = self.dataflow.extra_grid_config
        if self.dataflow.component_config:
            temp_display_args['main']['df_viewer_config']['component_config'] = self.dataflow.component_config

        self.df_display_args = temp_display_args


    def __init__(self, orig_df, debug=False,
        column_config_overrides:Union[Literal[None], OverrideColumnConfig]=None,
        pinned_rows:Union[Literal[None], PinnedRowConfig]=None, extra_grid_config=None,
        component_config:Union[Literal[None], ComponentConfig]=None,
        init_sd=None, record_transcript=False):
        super().__init__(orig_df, debug, column_config_overrides, pinned_rows,
                         extra_grid_config, component_config, init_sd,
                         skip_main_serial=True, record_transcript=record_transcript)

        def widget_tuple_args_bridge(change_unused):
            self._handle_widget_change(change_unused)
        self.dataflow.observe(widget_tuple_args_bridge, "widget_args_tuple")
        def payload_bridge(_unused_self, msg, _unused_buffers):
            if msg['type'] == 'infinite_request':
                payload_args = msg['payload_args']
                self._handle_payload_args(payload_args)

        self.on_msg(payload_bridge)

    def _handle_payload_args(self, new_payload_args):
        start, end = new_payload_args['start'], new_payload_args['end']
        _unused, processed_df, merged_sd = self.dataflow.widget_args_tuple
        if processed_df is None:
            return

        try:
            sort = new_payload_args.get('sort')
            if sort:
                sort_dir = new_payload_args.get('sort_direction')
                ascending = sort_dir == 'asc'
                processed_sd = self.dataflow.widget_args_tuple[2]
                converted_sort_column = processed_sd[sort]['orig_col_name']
                sorted_df = processed_df.sort_values(by=[converted_sort_column], ascending=ascending)
                slice_df = sorted_df[start:end]
                self.send({ "type": "infinite_resp", 'key':new_payload_args, 'data':[], 'length':len(processed_df)}, [to_parquet(slice_df)])
            else:
                slice_df = processed_df[start:end]
                self.send({ "type": "infinite_resp", 'key':new_payload_args,
                            'data': [], 'length':len(processed_df)}, [to_parquet(slice_df) ])
    
                second_pa = new_payload_args.get('second_request')
                if not second_pa:
                    return
                
                extra_start, extra_end = second_pa.get('start'), second_pa.get('end')
                extra_df = processed_df[extra_start:extra_end]
                self.send(
                    {"type": "infinite_resp", 'key':second_pa, 'data':[], 'length':len(processed_df)},
                    [to_parquet(extra_df)]
                )
        except Exception as e:
            logger.error(e)
            stack_trace = traceback.format_exc()
            self.send({ "type": "infinite_resp", 'key':new_payload_args, 'data':[], 'error_info':stack_trace, 'length':0})
            raise


    def _df_to_obj(self, df:pd.DataFrame):
        return pd_to_obj(df)

class DFViewerInfinite(BuckarooInfiniteWidget):
    

    render_func_name = Unicode("DFViewerInfinite").tag(sync=True)
    df_id = Unicode("unknown").tag(sync=True)

    def __init__(self, orig_df, debug=False,
        column_config_overrides:Union[Literal[None], OverrideColumnConfig]=None,
        pinned_rows:Union[Literal[None], PinnedRowConfig]=None, extra_grid_config=None,
        component_config:Union[Literal[None], ComponentConfig]=None,
        init_sd=None):
        super().__init__(orig_df, debug, column_config_overrides, pinned_rows,
                         extra_grid_config, component_config, init_sd)
        self.df_id = str(id(orig_df))


class AutocleaningBuckaroo(BuckarooInfiniteWidget):
    autoclean_conf = tuple([NoCleaningConf, AggressiveAC, ConservativeAC])
    analysis_klasses = copy_extend(
        BuckarooInfiniteWidget.analysis_klasses, CleaningDetailStyling
    )
