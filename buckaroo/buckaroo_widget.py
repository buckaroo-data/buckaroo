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
from .customizations.all_transforms import DefaultCommandKlsList


from .customizations.analysis import (TypingStats, ComputedDefaultSummaryStats, DefaultSummaryStats)
from .customizations.histogram import (Histogram)
from .customizations.styling import (DefaultSummaryStatsStyling, DefaultMainStyling)
from .pluggable_analysis_framework.analysis_management import DfStats
from .pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis

from .serialization_utils import EMPTY_DF_WHOLE
from .dataflow.dataflow import CustomizableDataflow, StylingAnalysis, exception_protect
from .dataflow.dataflow_extras import (Sampling)

class BuckarooProjectWidget(DOMWidget):
    """
    Repetitious code needed to make Jupyter communicate properly with any BuckarooWidget in this package
    
    """
    _model_module = Unicode(module_name).tag(sync=True)
    _view_module  = Unicode(module_name).tag(sync=True)

    _model_module_version = Unicode(module_version).tag(sync=True)
    _view_module_version  = Unicode(module_version).tag(sync=True)



class PdSampling(Sampling):
        #pre_limit = 500_000
        pre_limit = False

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

    operations = List().tag(sync=True)
    operation_results = Dict(
        {'transformed_df': EMPTY_DF_WHOLE, 'generated_py_code':'# instantiation, unused'}
    ).tag(sync=True)

    df_meta = Dict({
        'columns': 5,
        'rows_shown': 20,
        'total_rows': 877}).tag(sync=True)


    buckaroo_state = Dict({
        'auto_clean': 'conservative',
        'post_processing': '',
        'sampled': False,
        'show_commands': False,
        'df_display': 'main',
        'search_string': '',
    }).tag(sync=True)


    @observe('buckaroo_state')
    @exception_protect('buckaroo_state-protector')
    def _buckaroo_state(self, change):
        #how to control ordering of column_config???
        # dfviewer_config = self._get_dfviewer_config(self.merged_sd, self.style_method)
        # self.widget_args_tuple = [self.processed_df, self.merged_sd, dfviewer_config]
        old, new = change['old'], change['new']
        if not old['post_processing'] == new['post_processing']:
            self.post_processing_method = new['post_processing']


        
    #widget config.  Change these via inheritance to alter core behaviors of buckaroo
    command_klasses = DefaultCommandKlsList
    analysis_klasses = [TypingStats, DefaultSummaryStats,
                        Histogram,
                        ComputedDefaultSummaryStats,
                        StylingAnalysis,
                        DefaultSummaryStats,
                        DefaultSummaryStatsStyling, DefaultMainStyling]


    DFStatsClass = DfStats


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
    _model_name = Unicode('DFViewerModel').tag(sync=True)
    _view_name = Unicode('DFViewerView').tag(sync=True)
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


