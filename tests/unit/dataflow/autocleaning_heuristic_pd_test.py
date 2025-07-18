import pandas as pd
from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)
from buckaroo.pluggable_analysis_framework.col_analysis import (ColAnalysis)
from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.dataflow.autocleaning import PandasAutocleaning
from buckaroo.customizations.pandas_commands import (
    SafeInt, DropCol, FillNA, GroupBy, NoOp, Search)
from buckaroo.customizations.pandas_cleaning_commands import (
    IntParse, StripIntParse, StrBool, USDate)
from buckaroo.customizations.pd_autoclean_conf import (NoCleaningConf)
from buckaroo.auto_clean.heuristic_lang import get_top_score
from buckaroo.jlisp.lisp_utils import s
import re

dirty_df = pd.DataFrame(
    {'a':[10,  20,  30,   40,  10, 20.3,   5, None, None, None],
     'b':["3", "4", "a", "5", "5",  "b", "b", None, None, None]})


def make_default_analysis(**kwargs):
    class DefaultAnalysis(ColAnalysis):
        requires_summary = []
        provides_defaults = kwargs
    return DefaultAnalysis

class CleaningGenOps(ColAnalysis):
    requires_summary = ['int_parse_fail', 'int_parse']
    provides_defaults = {'cleaning_ops': []}

    int_parse_threshhold = .3
    @classmethod
    def computed_summary(kls, column_metadata):
        if column_metadata['int_parse'] > kls.int_parse_threshhold:
            return {'cleaning_ops': [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}],
                    'add_orig': True}
        else:
            return {'cleaning_ops': []}


class ACConf(AutocleaningConfig):
    autocleaning_analysis_klasses = [DefaultSummaryStats, CleaningGenOps, PdCleaningStats]
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name="default"


EXPECTED_GEN_CODE = """def clean(df):
    df['a'] = smart_to_int(df['a'])
    return df"""

def test_autoclean_codegen():
    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    assert generated_code == EXPECTED_GEN_CODE


def int_parse_frac(ser):
    null_count =  (~ ser.apply(pd.to_numeric, errors='coerce').isnull()).sum()
    return  null_count / len(ser)

digits_and_period = re.compile(r'[^\d\.]')
def strip_int_parse_frac(ser):
    stripped = ser.str.replace(digits_and_period, "", regex=True)

    #don't like the string conversion here, should still be vectorized
    int_parsable = ser.astype(str).str.isdigit() 
    parsable = (int_parsable | (stripped != ""))
    return parsable.sum() / len(ser)


TRUE_SYNONYMS = ["true", "yes", "on", "1"]
FALSE_SYNONYMS = ["false", "no", "off", "0"]
BOOL_SYNONYMS = TRUE_SYNONYMS + FALSE_SYNONYMS

def str_bool_frac(ser):
    matches = ser.str.lower().isin(BOOL_SYNONYMS)
    return matches.sum() / len(ser)

def us_dates_frac(ser):
    parsed_dates = pd.to_datetime(ser, errors='coerce', format="%m/%d/%Y")
    return (~ parsed_dates.isna()).sum() / len(ser)

def euro_dates_frac(ser):
    parsed_dates = pd.to_datetime(ser, errors='coerce', format="%d/%m/%Y")
    return (~ parsed_dates.isna()).sum() / len(ser)



class HeuristicFracs(ColAnalysis):

    provides_defaults = dict(
        str_bool_frac=0, regular_int_parse_frac=0, strip_int_parse_frac=0, us_dates_frac=0)

    @staticmethod
    def series_summary(sampled_ser, ser):
        if not pd.api.types.is_string_dtype(ser):
            return {}
        
        return dict(
            str_bool_frac=str_bool_frac(ser),
            regular_int_parse_frac=int_parse_frac(ser),
            strip_int_parse_frac=strip_int_parse_frac(ser),
            us_dates_frac=us_dates_frac(ser))


class HeuristicCleaningGenOps(ColAnalysis):
    """
    This class is meant to be extended with idfferent rules passed in

    create other ColAnalysis classes that satisfy requires_summary

    Then put this group of classes into their own AutocleaningConfig
    """
    requires_summary = ['str_bool_frac', 'regular_int_parse_frac', 'strip_int_parse_frac', 'us_dates_frac']
    provides_defaults = {'cleaning_ops': []}

    rules = {
        'str_bool_frac':          [s('f>'), .7],
        'regular_int_parse_frac': [s('f>'), .9],
        'strip_int_parse_frac':   [s('f>'), .7],
        'none':                   [s('none-rule')],
        'us_dates_frac':          [s('primary'), [s('f>'), .7]]}

    rules_op_names = {
        'str_bool_frac': 'str_bool',
        'regular_int_parse_frac': 'regular_int_parse',
        'strip_int_parse_frac':    'strip_int_parse',
        'us_dates_frac':         'us_date'}


    @classmethod
    def computed_summary(kls, column_metadata):

        cleaning_op_name = get_top_score(kls.rules, column_metadata)
        if cleaning_op_name == 'none':
            return {'cleaning_ops': []}
        else:
            ops = [
                {'symbol': kls.rules_op_names.get(cleaning_op_name, cleaning_op_name),
                 'meta':{ 'auto_clean': True, 'clean_strategy': kls.__name__}},
                {'symbol': 'df'}]
            print("ops", ops)

            return {'cleaning_ops':ops, 'add_orig': True}


class ACHeuristic(AutocleaningConfig):
    """
    add a check between rules_op_names to all of the included command classes
    """
    autocleaning_analysis_klasses = [HeuristicFracs, HeuristicCleaningGenOps]
    command_klasses = [
        IntParse, StripIntParse, StrBool, USDate,
        DropCol, FillNA, GroupBy, NoOp,
        Search]
    
    quick_command_klasses = [Search]
    name="default"


EXPECTED_GEN_CODE2 = """def clean(df):
    df['a'] = df['a'].apply(pd.to_numeric, errors='coerce')
    return df"""

def test_heuristic_autoclean_codegen():
    ac = PandasAutocleaning([ACHeuristic, NoCleaningConf])
    df = pd.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    assert generated_code == EXPECTED_GEN_CODE2
