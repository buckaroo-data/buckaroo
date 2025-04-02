import json
import pandas as pd
from buckaroo.jlisp.lisp_utils import split_operations, s, qc_sym
from buckaroo.pluggable_analysis_framework.analysis_management import DfStats
from ..customizations.all_transforms import configure_buckaroo, DefaultCommandKlsList

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

    def __init__(self, confs):
        self.command_config = {}
    
    def handle_ops_and_clean(self, df, cleaning_method, quick_command_args, existing_operations):
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
    merged.extend(user_gen_ops)  # we want the user cleaning ops to come last
    return merged



def format_ops(column_meta):
    """
    translate summary_dict with cleaning_ops to real, usable instructions
    """
    ret_ops = []
    for k,v in column_meta.items():
        if k == 'index':
            continue
        if 'cleaning_ops' not in v:
            continue
        ops = v['cleaning_ops']
        if len(ops) > 0:
            temp_ops = ops.copy()
            temp_ops.insert(2, k)
            ret_ops.append(temp_ops)
    return ret_ops

def ops_eq(ops_a, ops_b):
    return json.dumps(ops_a) == json.dumps(ops_b)

class AutocleaningConfig:
    command_klasses = [DefaultCommandKlsList]
    autocleaning_analysis_klasses = []
    quick_command_klasses = []
    name = 'default'
    
    
class WrongFrontendQuickArgs(Exception):
    pass

def generate_quick_ops(command_list, quick_args):
    ret_ops = []
    for c in command_list:
        sym_name = c.command_default[0]['symbol']
        if sym_name not in quick_args:
            continue
        val = quick_args[sym_name]
        if len(val) == 1:
            v1 = val[0]
            if v1 == "" or v1 is None:
                #this is an empty result sent from the frontend.
                #the frontend for quick_args is pretty dumb
                continue 
        if not len(val) == len(c.quick_args_pattern):
            raise WrongFrontendQuickArgs(f"Frontend passed in wrong quick_arg format for {sym_name} expected {c.quick_args_pattern} got {val}.  Full quick_args obj {quick_args}")
        op = c.command_default.copy()
        for form, arg  in zip(c.quick_args_pattern, val):
            arg_pos = form[0]
            op[arg_pos] = arg
        op[0] = qc_sym(sym_name)
        ret_ops.append(op)
    return ret_ops

            

class PandasAutocleaning:
    # def add_command(self, incomingCommandKls):
    #     without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
    #     without_incoming.append(incomingCommandKls)
    #     self.command_klasses = without_incoming
    #     self.setup_from_command_kls_list()

    DFStatsKlass = DfStats
    #until we plumb in swapping configs, just stick with default
    def __init__(self, ac_configs=tuple([AutocleaningConfig()]), conf_name="NoCleaning"):

        self.config_dict = {}
        for conf in ac_configs:
            self.config_dict[conf.name] = conf
        self._setup_from_command_kls_list(conf_name)

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
        self.command_config = dict(argspecs=c_patterns, defaultArgs=c_defaults)
        self.quick_command_klasses = conf.quick_command_klasses


    def _run_df_interpreter(self, df, operations):
        full_ops = [{'symbol': 'begin'}]

        def wrap_set_df(form):
            """
            wrap each passed in form with a set! call to update the df symbol
            """
            return [s("set!"), s("df"), form]
        full_ops.extend(map(wrap_set_df, operations))
        full_ops.append(s("df"))
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

        #cleaning_sd = {}
        return gen_ops, dfs.sdf

    @staticmethod
    def make_origs(raw_df, cleaned_df, cleaning_sd):
        cols = {}

        changed = 0
        for col, sd in cleaning_sd.items():
            if col not in cleaned_df.columns:
                continue
            if col == 'index':
                continue
            if "add_orig" in sd:
                cols[col] = cleaned_df[col]
                cols[col + "_orig"] = raw_df[col]
                changed += 1
            else:
                cols[col] = cleaned_df[col]
        if changed > 0:
            return pd.DataFrame(cols)
        else:
            return cleaned_df

    def produce_cleaning_ops(self, df, cleaning_method):
        """
        I probably want to cache this

        """
        if df is None:
            #on first instantiation df is likely to be None,  do nothing and return
            return [], {}

        if cleaning_method == "":
            return [], {}
        self._setup_from_command_kls_list(cleaning_method)
        cleaning_operations, cleaning_sd = self._run_cleaning(df, cleaning_method)
        return cleaning_operations, cleaning_sd

    def produce_final_ops(self, cleaning_ops, quick_command_args, existing_operations):
        quick_ops = generate_quick_ops(self.quick_command_klasses, quick_command_args)
        cleaning_ops.extend(quick_ops)
        merged_operations = merge_ops(existing_operations, cleaning_ops)
        return merged_operations
    

    def handle_ops_and_clean(self, df, cleaning_method, quick_command_args, existing_operations):
        if df is None:
            #on first instantiation df is likely to be None,  do nothing and return
            return None

        cleaning_ops, cleaning_sd = self.produce_cleaning_ops(df, cleaning_method)

        # [{'meta':'no-op'}] is a sentinel for the initial state
        if ops_eq(existing_operations, [{'meta':'no-op'}]) and cleaning_method == "NoCleaning":
            final_ops = self.produce_final_ops(cleaning_ops, quick_command_args, [])
            #FIXME, a little bit of a hack to reset cleaning_sd, but it helps tests pass. I
            # don't know how any other properties could really be set
            # when 'no-op' the initial state is true
            cleaning_sd = {}
        else:
            final_ops = self.produce_final_ops(cleaning_ops, quick_command_args, existing_operations)

        if ops_eq(final_ops,[]) and cleaning_method == "NoCleaning":
            #nothing to be done here, no point in running the interpreter
            #this also has the nice effect of not copying the DF, which the interpreter does
            return [df, {}, "", []]


        cleaned_df = self._run_df_interpreter(df, final_ops)
        merged_cleaned_df = self.make_origs(df, cleaned_df, cleaning_sd)
        generated_code = self._run_code_generator(final_ops)
        return [merged_cleaned_df, cleaning_sd, generated_code, final_ops]

