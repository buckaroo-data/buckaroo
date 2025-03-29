import six
import warnings
import pandas as pd
from traitlets import Unicode, Any, observe, HasTraits, Dict
from ..serialization_utils import pd_to_obj    
from buckaroo.pluggable_analysis_framework.utils import (filter_analysis)
from buckaroo.pluggable_analysis_framework.analysis_management import DfStats
from .autocleaning import SentinelAutocleaning
from .dataflow_extras import (
    EMPTY_DF_DISPLAY_ARG, merge_sds, merge_column_config,
    style_columns, exception_protect, StylingAnalysis,
    Sampling)




class DataFlow(HasTraits):
    """This class is meant to only represent the dataflow through
    buckaroo with no accomodation for widget particulars

    It generally has stub methods for implementations that enable basic testing of the 'data flow' .
    It is meant to be extended by Customizable DataFlow that can specify multiple different options

    CustomizableDataflow is meant to be extended by BuckarooWidget whcih connects frontend values to the following properties

    sample_method
    cleaning_method
    existing_operations
    style_method ... became df_display_args

    all of this results in values for df_dict being updated
    
    """
    def __init__(self, raw_df):
        self.exception = None
        super().__init__()
        self.summary_sd = {}
        self.existing_operations = []
        self.ac_obj = self.autocleaning_klass(self.autoclean_conf)
        self.command_config = self.ac_obj.command_config
        try:
            self.raw_df = raw_df
        except Exception:
            six.reraise(self.exception[0], self.exception[1], self.exception[2])

    autocleaning_klass = SentinelAutocleaning
    autoclean_conf = tuple()

    command_config = Dict({}).tag(sync=True)
    operation_results = Dict({'transformed_df':None,
                              'generated_py_code': ""})


    raw_df = Any('')
    sample_method = Unicode('default')
    sampled_df = Any('')

    cleaning_method = Unicode('NoCleaning')
    quick_command_args = Dict({})

    # we put an operation here that will be stripped out, this assures
    # us that the interpeter is run through at least once
    operations = Any([]).tag(sync=True)

    cleaned = Any().tag(default=None)
    
    post_processing_method = Unicode('').tag(default='')
    processed_result = Any().tag(default=None)

    analysis_klasses = None
    summary_sd = Any()
    df_meta = Any()

    merged_sd = Any()

    style_method = Unicode('simple')
    column_config = Any()

    column_config_overrides = {}

    merged_column_config = Any()

    widget_args_tuple = Any()


    
    def _compute_sampled_df(self, raw_df, sample_method):
        if sample_method == "first":
            return raw_df[:1]
        return raw_df


    @observe('raw_df', 'sample_method')
    @exception_protect('sampled_df-protector')
    def _sampled_df(self, change):
        self.sampled_df = self._compute_sampled_df(self.raw_df, self.sample_method)

    @observe('sampled_df', 'cleaning_method', 'quick_command_args', 'operations')
    @exception_protect('operation_result-protector')
    def _operation_result(self, change):
        """This function is really complex

        three main pieces with operations interact here.

        Cleaning method generates operations, quick_command_args
        generates operations, and then there are the existing
        operations

        Operations that are created by quick_command_args, and
        cleaning_method ar called generated_ops and are treated differently than operations
        created by the user. Generated_ops are tagged with meta: {'auto_clean':True}
        and or meta: 'quick_command:True.  User created oeprations have no meta key

        So if the user changes "cleaning_method", all existing
        generated_ops are removed, new generated_ops are created and
        merged with the existing user_operations

        These merged operations are then set back onto the "self.operations" trait.

        Obviously this can lead to cycles so this code must be approached carefully

        """
        result = self.ac_obj.handle_ops_and_clean(
            self.sampled_df, self.cleaning_method, self.quick_command_args, self.operations)

        if result is None:
            return
        else:
            self.cleaned = result
            self.operations = result[3]
        self.operation_results = {'transformed_df':None,
                                  'generated_py_code': self.generated_code,
                                  }

    @property
    def cleaned_df(self):
        if self.cleaned is not None:
            return self.cleaned[0]

    @property
    def cleaned_sd(self):
        if self.cleaned is not None:
            return self.cleaned[1]
        return {}

    @property
    def generated_code(self):
        if self.cleaned is not None:
            return self.cleaned[2]

    @property
    def merged_operations(self):
        if self.cleaned is not None:
            return self.cleaned[3]

    def _compute_processed_result(self, cleaned_df, post_processing_method):
        return [cleaned_df, {}]

    def populate_df_meta(self):
        pass

    @observe('cleaned', 'post_processing_method')
    @exception_protect('processed_result-protector')
    def _processed_result(self, change):
        #for now this is a no-op because I don't have a post_processing_function or mechanism
        self.processed_result = self._compute_processed_result(self.cleaned_df, self.post_processing_method)
        self.populate_df_meta()

    @property
    def processed_df(self):
        if self.processed_result is not None:
            return self.processed_result[0]
        return None

    @property
    def processed_sd(self):
        if self.processed_result is not None:
            return self.processed_result[1]
        return {}

    def _get_summary_sd(self, df):
        analysis_klasses = self.analysis_klasses
        if analysis_klasses == "foo":
            return {'some-col': {'foo':8}}, {}
        if analysis_klasses == "bar":
            return {'other-col': {'bar':10}}, {}
        index_name = df.index.name or "index"
        ret_summary = {index_name: {}}
        for col in df.columns:
            ret_summary[col] = {}
        return ret_summary, {}

    @observe('processed_result', 'analysis_klasses')
    @exception_protect('summary_sd-protector')
    def _summary_sd(self, change):
        result_summary_sd, errs  = self._get_summary_sd(self.processed_df)
        self.summary_sd = result_summary_sd
        self.errs = errs

    @observe('summary_sd', 'processed_result')
    @exception_protect('merged_sd-protector')
    def _merged_sd(self, change):
        #slightly inconsitent that processed_sd gets priority over
        #summary_sd, given that processed_df is computed first. My
        #thinking was that processed_sd has greater total knowledge
        #and should supersede summary_sd.
        self.merged_sd = merge_sds(self.cleaned_sd, self.summary_sd, self.processed_sd)

    def _get_dfviewer_config(self, sd, style_method):
        dfviewer_config = style_columns(style_method, sd)
        base_column_config = dfviewer_config['column_config']
        dfviewer_config['column_config'] =  merge_column_config(
            base_column_config, self.column_config_overrides)
        return dfviewer_config

    @observe('merged_sd', 'style_method')
    @exception_protect('widget_config-protector')
    def _widget_config(self, change):
        #how to control ordering of column_config???
        # dfviewer_config = self._get_dfviewer_config(self.merged_sd, self.style_method)
        # self.widget_args_tuple = [self.processed_df, self.merged_sd, dfviewer_config]
        self.widget_args_tuple = (id(self.processed_df), self.processed_df, self.merged_sd)


class CustomizableDataflow(DataFlow):
    """
    This allows targetd extension and customization of DataFlow
    """
    analysis_klasses = [StylingAnalysis]
    command_config = Dict({}).tag(sync=True)
    DFStatsClass = DfStats
    sampling_klass = Sampling
    df_display_klasses = {}
    operations = Any([{'meta':'no-op'}]).tag(sync=True)

    def __init__(self, orig_df, debug=False,
                 column_config_overrides=None,
                 pinned_rows=None, extra_grid_config=None,
                 component_config=None, init_sd=None, skip_main_serial=False):
        if init_sd is None:
            self.init_sd = {}
        else:
            self.init_sd = init_sd
        self.skip_main_serial = skip_main_serial
        if column_config_overrides is None:
            column_config_overrides = {}
        self.column_config_overrides = column_config_overrides
        self.pinned_rows = pinned_rows
        self.extra_grid_config = extra_grid_config
        self.component_config = component_config
        if not debug:
            warnings.filterwarnings('ignore')

        self.debug = debug
        #self.df_name = get_df_name(df)
        self.df_name = "placeholder"
        self.df_display_args = {}
        self.setup_options_from_analysis()
        self.orig_df = orig_df
        # I don't like this seapration of 
        super().__init__(self.sampling_klass.pre_stats_sample(orig_df))
        self.populate_df_meta()
        #self.raw_df = df
        warnings.filterwarnings('default')

    def populate_df_meta(self):
        if self.processed_df is None:
            self.df_meta = {
                'columns': 0,
                # I need to recompute this when sampling changes
                'filtered_rows': 0,
                'rows_shown': 0,
                'total_rows': 0}

            return
        self.df_meta = {
            'columns': len(self.processed_df.columns),
            # I need to recompute this when sampling changes
            'filtered_rows': len(self.processed_df),
            'rows_shown': min(len(self.processed_df), self.sampling_klass.serialize_limit),  
            'total_rows': len(self.orig_df)}

    buckaroo_options = Dict({
        'sampled': ['random'],
        'auto_clean': ['aggressive', 'conservative'],
        'post_processing': [],
        'df_display': ['main', 'summary'],
        'show_commands': ['on'],
        'summary_stats': ['all'],
    }).tag(sync=True)

    def setup_options_from_analysis(self):
        self.df_display_klasses = filter_analysis(self.analysis_klasses, "df_display_name")
        #add a check to verify that there aren't multiple classes offering the same df_display_name

        empty_df_display_args = {}
        for k, kls in self.df_display_klasses.items():
            empty_df_display_args[kls.df_display_name] = EMPTY_DF_DISPLAY_ARG


        self.DFStatsClass.verify_analysis_objects(self.analysis_klasses)

        self.post_processing_klasses = filter_analysis(self.analysis_klasses, "post_processing_method")

        new_buckaroo_options = self.buckaroo_options.copy()
        new_buckaroo_options['df_display'] = list(self.df_display_klasses.keys())
        post_processing_methods = ['']
        post_processing_methods.extend(list(self.post_processing_klasses.keys()))
        new_buckaroo_options['post_processing'] = post_processing_methods
        #important that we open up the possibilities first before we add them as options in the UI
        self.df_display_args = empty_df_display_args
        self.buckaroo_options = new_buckaroo_options

    df_display_args = Any({'main':EMPTY_DF_DISPLAY_ARG}).tag(sync=True)
    #empty needs to always be present, it enables startup
    df_data_dict = Any({'empty':[]}).tag(sync=True)


    @observe('summary_sd', 'processed_result')
    @exception_protect('merged_sd-protector')
    def _merged_sd(self, change):
        #slightly inconsitent that processed_sd gets priority over
        #summary_sd, given that processed_df is computed first. My
        #thinking was that processed_sd has greater total knowledge
        #and should supersede summary_sd.
        self.merged_sd = merge_sds(self.init_sd, self.cleaned_sd, self.summary_sd, self.processed_sd)


    ### start code interpreter block
    def add_command(self, incomingCommandKls):
        return self.ac_obj.add_command(incomingCommandKls)

    def _run_df_interpreter(self, df, operations):
        self.ac_obj._run_df_interpreter(df, operations)

    def run_code_generator(self, operations):
        self.ac_obj.run_code_generator(operations)
    ### end code interpeter block

    def _compute_processed_result(self, cleaned_df, post_processing_method):
        if post_processing_method == '':
            return [cleaned_df, {}]
        else:
            post_analysis = self.post_processing_klasses[post_processing_method]
            try:
                ret_df, sd =  post_analysis.post_process_df(cleaned_df)
                return (ret_df, sd)
            except Exception as e:
                return (self._build_error_dataframe(e), {})

    def _build_error_dataframe(self, e):
        return pd.DataFrame({'err': [str(e)]})


    ### start summary stats block

    def _get_summary_sd(self, processed_df):
        stats = self.DFStatsClass(
            processed_df,
            self.analysis_klasses,
            self.df_name, debug=self.debug)
        sdf = stats.sdf
        if stats.errs:
            if self.debug:
                raise Exception("Error executing analysis")
            else:
                return {}, stats.errs
        else:
            return sdf, {}


    # ### end summary stats block        

    def _sd_to_jsondf(self, sd):
        """exists so this can be overriden for polars  """
        temp_sd = sd.copy()
        #FIXME add actual test around weird index behavior
        if 'index' in temp_sd:
            del temp_sd['index']
        return self._df_to_obj(pd.DataFrame(temp_sd))

    def _df_to_obj(self, df:pd.DataFrame):
        return pd_to_obj(self.sampling_klass.serialize_sample(df))
    
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
        self.DFStatsClass.verify_analysis_objects(self.analysis_klasses)
        self.setup_options_from_analysis()
        #force recomputation
        self._handle_widget_change({})


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
        if self.skip_main_serial:
            self.df_data_dict = {'main': [],
                                 'all_stats': self._sd_to_jsondf(merged_sd),
                                 'empty': []}
        else:
            self.df_data_dict = {'main': self._df_to_obj(processed_df),
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
   
"""


Instantiation
df_data_dict starts with only 'empty'
first populate df_display_args, make all data point to 'empty', make all df_viewer_configs EMPTY_DFVIEWER_CONFIG

then populate buckaroo_options['df_display'] from gathered classes

Next add 'all_stats' to 'df_data_dict'
add 'main' to 'df_data_dict'


all of the above steps might trigger redisplays, but they will be cheap because df_viewer_config will be empty, pointing at empty data

finally iterate through all 'df_display' analysis_klasses and update df_display_args





"""
