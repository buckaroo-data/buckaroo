import pandas as pd
from buckaroo.jlisp.lisp_utils import split_operations
#from buckaroo.pluggable_analysis_framework.polars_analysis_management import PlDfStats
from buckaroo.pluggable_analysis_framework.analysis_management import DfStats
from ..customizations.all_transforms import configure_buckaroo, DefaultCommandKlsList


'''


    def handle_ops_and_clean_orig(self, df, cleaning_method, existing_operations):
        if self.sampled_df is None:
            return None
        cleaning_operations, cleaning_sd = self._run_cleaning(df, cleaning_method)
        merged_operations = merge_ops(existing_operations, cleaning_operations)
        cleaned_df = self._run_df_interpreter(df, merged_operations)
        generated_code = self._run_code_generator(merged_operations)
        self.cleaned [cleaned_df, cleaning_sd, generated_code, merged_operations]


'''
def dumb_merge_ops(existing_ops, cleaning_ops):
    """ strip cleaning_ops from existing_ops, reinsert cleaning_ops at the beginning """
    a = existing_ops.copy()
    a.extend(cleaning_ops)
    return a

SENTINEL_DF_1 = pd.DataFrame({'foo'  :[10, 20], 'bar' : ["asdf", "iii"]})
SENTINEL_DF_2 = pd.DataFrame({'col1' :[55, 55], 'col2': ["pppp", "333"]})
SENTINEL_DF_3 = pd.DataFrame({'pp'   :[99, 33], 'ee':   [     6,     9]})
SENTINEL_DF_4 = pd.DataFrame({'vvv'  :[12, 49], 'oo':   [ 'ccc', 'www']})

class SentinelAutocleaning:

    def handle_ops_and_clean(self, df, cleaning_method, existing_operations):
        cleaning_ops = []
        generated_code = ""
        if cleaning_method == "one op":
            cleaning_ops =  [""]
            generated_code = "codegen 1"
            generated_code = "codegen 2"
        elif cleaning_method == "two op":
            cleaning_ops = ["", ""]

        merged_operations = dumb_merge_ops(existing_operations, cleaning_ops)
        
        if len(merged_operations) == 1:
            cleaned_df = SENTINEL_DF_1
        elif len(merged_operations) == 2:
            cleaned_df = SENTINEL_DF_2
        else:
            cleaned_df = df
        return [cleaned_df, {}, generated_code, merged_operations]

def merge_ops(existing_ops, cleaning_ops):
    """ strip cleaning_ops from existing_ops, reinsert cleaning_ops at the beginning """
    old_cleaning_ops, user_gen_ops = split_operations(existing_ops)
    merged = cleaning_ops.copy()
    merged.extend(user_gen_ops)
    return merged



def format_ops(column_meta):
    ret_ops = []
    for k,v in column_meta.items():
        ops = v['cleaning_ops']
        if len(ops) > 0:
            temp_ops = ops.copy()
            temp_ops.insert(2, k)
            ret_ops.append(temp_ops)
    return ret_ops

def make_origs(raw_df, cleaned_df):
    clauses = []
    for col in raw_df.columns:
        clauses.append(cleaned_df[col])
        clauses.append(raw_df[col].alias(col+"_orig"))
        # clauses.append(
        #     pl.when((raw_df[col] - cleaned_df[col]).eq(0)).then(None).otherwise(raw_df[col]).alias(col+"_orig"))
    ret_df = cleaned_df.select(clauses)
    return ret_df


class AutocleaningConfig:
    command_klasses = [DefaultCommandKlsList]
    autocleaning_analysis_klasses = []

    name = 'default'
    

class Autocleaning:
    # def add_command(self, incomingCommandKls):
    #     without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
    #     without_incoming.append(incomingCommandKls)
    #     self.command_klasses = without_incoming
    #     self.setup_from_command_kls_list()

    DFStatsKlass = DfStats
    def __init__(self, ac_configs):

        self.config_dict = {}
        for conf in ac_configs:
            self.config_dict[conf.name] = conf

    ### start code interpreter block
    def _setup_from_command_kls_list(self, name):
        #used to initially setup the interpreter, and when a command
        #is added interactively
        if name not in self.config_dict:
            options = list(self.config_dict.keys())
            raise Exception(
                "Unknown autocleaning conf of %s, available options are %r" % (name, options))
        conf = self.config_dict[name]
        c_klasses, self.autocleaning_analysis_klasses = conf.command_klasses, conf.autocleaning_analysis_klasses

        c_defaults, c_patterns, df_interpreter, gencode_interpreter = configure_buckaroo(c_klasses)
        self.df_interpreter, self.gencode_interpreter = df_interpreter, gencode_interpreter
        self.commandConfig = dict(argspecs=c_patterns, defaultArgs=c_defaults)


    def _run_df_interpreter(self, df, operations):
        full_ops = [{'symbol': 'begin'}]
        full_ops.extend(operations)
        print("*"*80)
        print(full_ops)
        print("*"*80)
        if len(full_ops) == 1:
            return df
        return self.df_interpreter(full_ops , df)

    def _run_code_generator(self, operations):
        if len(operations) == 0:
            return 'no operations'
        return self.gencode_interpreter(operations)

    def _run_cleaning(self, df, cleaning_method):
        dfs = self.DFStatsKlass(df, self.autocleaning_analysis_klasses, debug=True)
        gen_ops = format_ops(dfs.sdf)

        cleaning_sd = {}
        return gen_ops, cleaning_sd

    def handle_ops_and_clean(self, df, cleaning_method, existing_operations):
        if df is None:
            return None
        self._setup_from_command_kls_list(cleaning_method)
        cleaning_operations, cleaning_sd = self._run_cleaning(df, cleaning_method)
        merged_operations = merge_ops(existing_operations, cleaning_operations)
        cleaned_df = self._run_df_interpreter(df, merged_operations)
        merged_cleaned_df = make_origs(df, cleaned_df)
        generated_code = self._run_code_generator(merged_operations)
        return [merged_cleaned_df, cleaning_sd, generated_code, merged_operations]
