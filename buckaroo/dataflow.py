import six
import sys
import warnings
import pandas as pd
from traitlets import Unicode, Any, observe, HasTraits, Dict
from .serialization_utils import pd_to_obj    
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.pluggable_analysis_framework.analysis_management import DfStats
from .customizations.all_transforms import configure_buckaroo, DefaultCommandKlsList

SENTINEL_DF_1 = pd.DataFrame({'foo'  :[10, 20], 'bar' : ["asdf", "iii"]})
SENTINEL_DF_2 = pd.DataFrame({'col1' :[55, 55], 'col2': ["pppp", "333"]})
SENTINEL_DF_3 = pd.DataFrame({'pp'   :[99, 33], 'ee':   [     6,     9]})
SENTINEL_DF_4 = pd.DataFrame({'vvv'  :[12, 49], 'oo':   [ 'ccc', 'www']})




def merge_ops(existing_ops, cleaning_ops):
    """ strip cleaning_ops from existing_ops, reinsert cleaning_ops at the beginning """
    a = existing_ops.copy()
    a.extend(cleaning_ops)
    return a

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

def merge_sds(*sds):
    """merge sds with later args taking precedence

    sub-merging of "overide_config"??
    """
    base_sd = {}
    for sd in sds:
        for column in sd.keys():
            base_sd[column] = merge_column(base_sd.get(column, {}), sd[column])
    return base_sd

SENTINEL_COLUMN_CONFIG_1 = "ASDF"
SENTINEL_COLUMN_CONFIG_2 = "FOO-BAR"




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


def exception_protect(protect_name=None):
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

        try:
            self.raw_df = raw_df
        except Exception:
            six.reraise(self.exception[0], self.exception[1], self.exception[2])

    raw_df = Any('')
    sample_method = Unicode('default')
    sampled_df = Any('')

    cleaning_method = Unicode('')
    cleaning_operations = Any()

    existing_operations = Any([])
    merged_operations = Any()

    cleaned = Any().tag(default=None)
    
    lowcode_operations = Any()

    post_processing_method = Unicode('').tag(default='')
    processed_result = Any().tag(default=None)

    analysis_klasses = None
    summary_sd = Any()

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

    def _run_df_interpreter(self, df, ops):
        if len(ops) == 1:
            return SENTINEL_DF_1
        if len(ops) == 2:
            return SENTINEL_DF_2
        return df

    def _run_code_generator(self, ops):
        if len(ops) == 1:
            return "codegen 1"
        if len(ops) == 2:
            return "codegen 2"
        return ""

    def _run_cleaning(self, df, cleaning_method):
        cleaning_ops = []
        if cleaning_method == "one op":
            cleaning_ops =  [""]
        if cleaning_method == "two op":
            cleaning_ops = ["", ""]
        cleaning_sd = {}
        return cleaning_ops, cleaning_sd

    @observe('sampled_df', 'cleaning_method', 'existing_operations')
    @exception_protect('operation_result-protector')
    def _operation_result(self, change):
        if self.sampled_df is None:
            return
        cleaning_operations, cleaning_sd = self._run_cleaning(self.sampled_df, self.cleaning_method)
        merged_operations = merge_ops(self.existing_operations, cleaning_operations)
        cleaned_df = self._run_df_interpreter(self.sampled_df, merged_operations)
        generated_code = self._run_code_generator(merged_operations)
        self.cleaned = [cleaned_df, cleaning_sd, generated_code, merged_operations]

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

    @observe('cleaned', 'post_processing_method')
    @exception_protect('processed_result-protector')
    def _processed_result(self, change):
        #for now this is a no-op because I don't have a post_processing_function or mechanism
        self.processed_result = self._compute_processed_result(self.cleaned_df, self.post_processing_method)

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
            return {'some-col': {'foo':8}}
        if analysis_klasses == "bar":
            return {'other-col': {'bar':10}}
        index_name = df.index.name or "index"
        ret_summary = {index_name: {}}
        for col in df.columns:
            ret_summary[col] = {}
        return ret_summary

    @observe('processed_result', 'analysis_klasses')
    @exception_protect('summary_sd-protector')
    def _summary_sd(self, change):
        result_summary_sd = self._get_summary_sd(self.processed_df)
        self.summary_sd = result_summary_sd

    @observe('summary_sd')
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






class UnknownStyleMethod(Exception):
    def __init__(self, style_method, available_methods, analysis_klasses):
        self.style_method = style_method
        self.available_methods = available_methods
        self.msg =\
            "style_method of '{self.style_method}' not found in '{available_methods}', all analysis_klasses is []'"


class StylingAnalysis(ColAnalysis):
    provides_defaults = {}
    pinned_rows = []

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
    def style_columns(kls, sd):
        ret_col_config = []

        #this is necessary for polars to add an index column, which is
        #required so that summary_stats makes sense
        if 'index' not in sd:
            ret_col_config.append({'col_name': 'index', 'displayer_args': {'displayer': 'obj'}})
            
        for col in sd.keys():
            col_meta = sd[col]
            base_style = kls.style_column(col, col_meta)
            if 'column_config_override' in col_meta:
                base_style.update(col_meta['column_config_override'])
            ret_col_config.append(base_style)
            
        return {
            'pinned_rows': kls.pinned_rows,
            'column_config': ret_col_config}


def filter_analysis(klasses, attr):
    ret_klses = {}
    for k in klasses:
        attr_val = getattr(k, attr, None)
        if attr_val is not None:
            ret_klses[attr_val] = k
    return ret_klses
            
class PostProcessingException(Exception):
    pass

EMPTY_DFVIEWER_CONFIG = {
    'pinned_rows': [],
    'column_config': []}
EMPTY_DF_DISPLAY_ARG = {'data_key': 'empty', 'df_viewer_config': EMPTY_DFVIEWER_CONFIG,
                           'summary_stats_key': 'empty'}

class Sampling:

    max_columns      =     250
    pre_limit        = 100_000
    serialize_limit  =  10_000

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
            return df.sample(kls.serialize_limit)
        return df

class CustomizableDataflow(DataFlow):
    """
    This allows targetd extension and customization of DataFlow
    """
    analysis_klasses = [StylingAnalysis]
    command_klasses = DefaultCommandKlsList
    commandConfig = Dict({}).tag(sync=True)
    DFStatsClass = DfStats
    sampling_klass = Sampling
    df_display_klasses = {}

    def __init__(self, df, debug=False, column_config_overrides=None, pinned_rows=None):
        if column_config_overrides is None:
            column_config_overrides = {}
        self.column_config_overrides = column_config_overrides
        self.pinned_rows = pinned_rows
        if not debug:
            warnings.filterwarnings('ignore')

        self.debug = debug
        #self.df_name = get_df_name(df)
        self.df_name = "placeholder"
        self.df_display_args = {}
        self.setup_options_from_analysis()
        super().__init__(self.sampling_klass.pre_stats_sample(df))

        self._setup_from_command_kls_list()
        self.populate_df_meta()
        #self.raw_df = df
        warnings.filterwarnings('default')
    


    def populate_df_meta(self):
        self.df_meta = {
            'columns': len(self.raw_df.columns),
            # I need to recompute this when sampling changes
            'rows_shown': len(self.sampled_df),  
            'total_rows': len(self.raw_df)}

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


    ### start code interpreter block
    def _setup_from_command_kls_list(self):
        #used to initially setup the interpreter, and when a command
        #is added interactively
        c_klasses = self.command_klasses
        c_defaults, c_patterns, df_interpreter, gencode_interpreter = configure_buckaroo(c_klasses)
        self.df_interpreter, self.gencode_interpreter = df_interpreter, gencode_interpreter
        self.commandConfig = dict(argspecs=c_patterns, defaultArgs=c_defaults)

    def add_command(self, incomingCommandKls):
        without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
        without_incoming.append(incomingCommandKls)
        self.command_klasses = without_incoming
        self.setup_from_command_kls_list()

    def _run_df_interpreter(self, df, operations):
        full_ops = [{'symbol': 'begin'}]
        full_ops.extend(operations)
        if len(full_ops) == 1:
            return df
        return self.buckaroo_transform(full_ops , df)

    def run_code_generator(self, operations):
        if len(operations) == 0:
            return 'no operations'
        return self.gencode_interpreter(operations)
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
                return {}
        else:
            return sdf


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

        if self.pinned_rows:
            temp_display_args['main']['df_viewer_config']['pinned_rows'] = self.pinned_rows
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
