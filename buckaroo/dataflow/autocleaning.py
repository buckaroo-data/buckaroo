import pandas as pd
from buckaroo.jlisp.lisp_utils import s, sQ, merge_ops, format_ops, ops_eq
from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2
from ..customizations.all_transforms import configure_buckaroo, DefaultCommandKlsList
from ..df_util import old_col_new_col
from .styling_core import merge_sds


def _rekey_op_sd_to_internal(cleaning_sd, cleaned_df):
    """Rewrite orig-name keys (from op-contributed SDResult entries) onto
    buckaroo's internal a/b/c letter keys, so the updates merge into the
    matching analysis entry instead of sitting alongside as orphans.

    A Command's transform only sees orig column names, so an SDResult it
    returns is keyed by those. Analysis entries are keyed by the positional
    letter assigned by the analysis pipeline and always carry
    `rewritten_col_name` (set by both pandas and polars analysis
    management). The marker lets us skip analysis entries even when their
    key happens to equal an orig name elsewhere in the frame — e.g. cols
    ['b', 'foo'] yield internal a='b' and b='foo'; without the check, the
    analysis entry for internal 'b' would get merged into 'a' because
    rewrites['b']=='a', corrupting metadata.
    """
    rewrites = dict(old_col_new_col(cleaned_df))
    out = {}
    for col, kv in cleaning_sd.items():
        if 'rewritten_col_name' in kv:
            target = col
        else:
            target = rewrites.get(col, col)
        if target in out:
            out[target] = merge_sds({target: out[target]}, {target: kv})[target]
        else:
            out[target] = kv
    return out

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

def _identity(x):
    return x


class AutocleaningConfig:
    command_klasses = [DefaultCommandKlsList]
    autocleaning_analysis_klasses = []
    quick_command_klasses = []
    name = 'default'
    # Hooks bookending the lisp-interpreter call in _run_df_interpreter.
    # Default identity = current behaviour. Polars overrides with df.lazy()
    # / collect-if-LazyFrame so a multi-op pipeline materialises once
    # instead of after every command. See NoCleaningConfPl.
    lazy_enter = staticmethod(_identity)
    lazy_exit = staticmethod(_identity)
    
    
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
        op[0] = sQ(sym_name)
        ret_ops.append(op)
    return ret_ops

            

class PandasAutocleaning:
    # def add_command(self, incomingCommandKls):
    #     without_incoming = [x for x in self.command_classes if not x.__name__ == incomingCommandKls.__name__]
    #     without_incoming.append(incomingCommandKls)
    #     self.command_klasses = without_incoming
    #     self.setup_from_command_kls_list()

    DFStatsKlass = DfStatsV2
    #until we plumb in swapping configs, just stick with default
    def __init__(self, ac_configs=tuple([AutocleaningConfig()]), conf_name=""):

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
        self.lazy_enter = conf.lazy_enter
        self.lazy_exit = conf.lazy_exit


    def _run_df_interpreter(self, df, operations, initial_sd):
        full_ops = [{'symbol': 'begin'}]

        def wrap_set_df(form):
            """
            Wrap each form so its result threads through apply-result! before
            updating df. apply-result! is a per-call closure (built inside
            buckaroo_transform) that merges any SDResult into the live sd
            and returns the bare df; bare-df returns pass through unchanged.
            """
            return [s("set!"), s("df"),
                [s("apply-result!"), s("sd"), form]]
        full_ops.extend(map(wrap_set_df, operations))
        full_ops.append(s("df"))
        if not operations:
            # No-op short-circuit. Load-bearing for two reasons:
            #   1. self.df_interpreter does df.copy()/clone() unconditionally;
            #      a fresh df object churns DfTrait identity (`is not`
            #      comparison), fires traitlets observers, and triggers a
            #      frontend resync of unchanged data over the anywidget
            #      boundary.
            #   2. During widget init, where the `df` and `operations` traits
            #      can be set in either order, creating fresh objects on the
            #      no-op path cascaded into observer-chain infinite loops.
            #      Returning by reference here was the stable fix.
            # Return df and initial_sd untouched — nothing ran, nothing to
            # copy. Do NOT add deepcopy here "to preserve the contract"; the
            # contract is precisely "no ops → caller's objects come back as-is".
            return df, initial_sd

        # lazy_enter/lazy_exit are conf-provided hooks. Polars flips to
        # LazyFrame on entry and collects on exit (one materialisation per
        # pipeline instead of N). Pandas/xorq leave the defaults — identity.
        # Both hooks run *after* the no-op short-circuit above, so the
        # by-reference identity contract there is preserved.
        ret_df, ret_sd = self.df_interpreter(full_ops, self.lazy_enter(df), initial_sd)
        return self.lazy_exit(ret_df), ret_sd

    def _run_code_generator(self, operations):
        if len(operations) == 0:
            return 'no operations'
        return self.gencode_interpreter(operations)

    def _run_cleaning(self, df, cleaning_method):
        dfs = self.DFStatsKlass(df, self.autocleaning_analysis_klasses, debug=True)
        gen_ops = format_ops(dfs.sdf)
        return gen_ops, dfs.sdf

    @staticmethod
    def make_origs(raw_df, cleaned_df, cleaning_sd):
        cols = {}

        changed = 0
        for rewritten_col, sd in cleaning_sd.items():

            col = sd.get("orig_col_name")
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
        if ops_eq(existing_operations, [{'meta':'no-op'}]) and cleaning_method == "":
            final_ops = self.produce_final_ops(cleaning_ops, quick_command_args, [])
            #FIXME, a little bit of a hack to reset cleaning_sd, but it helps tests pass. I
            # don't know how any other properties could really be set
            # when 'no-op' the initial state is true
            cleaning_sd = {}
        else:
            final_ops = self.produce_final_ops(cleaning_ops, quick_command_args, existing_operations)
        if ops_eq(final_ops,[]) and cleaning_method == "":
            # No-op short-circuit. Returns `df` by reference — load-bearing
            # for the same reasons as _run_df_interpreter's short-circuit:
            # avoids df.copy() identity churn (traitlets + frontend resync)
            # and avoids the init-order observer-loop hazard. See the longer
            # explanation in _run_df_interpreter above.
            return [df, {}, "", []]


        cleaned_df, cleaning_sd = self._run_df_interpreter(df, final_ops, cleaning_sd)
        merged_cleaned_df = self.make_origs(df, cleaned_df, cleaning_sd)
        # Run rekey AFTER make_origs: the polars make_origs walks cleaning_sd
        # keys as actual column names on cleaned_df, so it needs op-supplied
        # entries to still be keyed by orig col name. After make_origs is
        # done with the df, rewrite the orig-keyed entries onto buckaroo's
        # internal a/b/c keys for the styling layer.
        cleaning_sd = _rekey_op_sd_to_internal(cleaning_sd, cleaned_df)
        generated_code = self._run_code_generator(final_ops)
        return [merged_cleaned_df, cleaning_sd, generated_code, final_ops]

