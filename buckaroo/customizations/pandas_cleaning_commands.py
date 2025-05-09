import pandas as pd
import re
from buckaroo.jlisp.lisp_utils import s
from buckaroo.customizations.pandas_commands import (Command)

class IntParse(Command):
    command_default = [s('regular_int_parse'), s('df'), "col"]
    command_pattern = []

    @staticmethod 
    def transform(df, col):
        df[col] = df[col].apply(pd.to_numeric, errors='coerce')
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = df['%s'].apply(pd.to_numeric, errors='coerce')" % (col, col)

class StripIntParse(Command):
    command_default = [s('strip_int_parse'), s('df'), "col"]
    command_pattern = []

    @staticmethod 
    def transform(df, col):
        _digits_and_period = re.compile(r'[^\d\.]')
        _ser = df[col]
        _reg_parse = _ser.apply(pd.to_numeric, errors='coerce')
        _strip_parse = _ser.str.replace(_digits_and_period, "", regex=True).apply(pd.to_numeric, errors='coerce', dtype_backend='pyarrow')
        _combined = _reg_parse.fillna(_strip_parse)
        df[col] = _combined.astype('Int64')
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return f"""    _digits_and_period = re.compile(r'[^\\d\\.]')
    _ser = df['{col}']
    _reg_parse = _ser.apply(pd.to_numeric, errors='coerce')
    _strip_parse = _ser.str.replace(_digits_and_period, "", regex=True).apply(pd.to_numeric, errors='coerce', dtype_backend='pyarrow')
    _combined = _reg_parse.fillna(_strip_parse)
    df['{col}'] = _combined"""


class StrBool(Command):
    command_default = [s('str_bool'), s('df'), "col"]
    command_pattern = []

    @staticmethod 
    def transform(df, col):
        TRUE_SYNONYMS = ['true', 'yes', 'on', '1']
        FALSE_SYNONYMS = ['false', 'no', 'off', '0']
        _ser = df[col]
        _int_sanitize = _ser.replace(1, True).replace(0, False) 
        _real_bools = _int_sanitize.isin([True, False])
        _boolean_ser = _int_sanitize.where(_real_bools, pd.NA).astype('boolean')
        _str_ser = _ser.str.lower().str.strip()
        _trues = _str_ser.isin(TRUE_SYNONYMS).replace(False, pd.NA).astype('boolean')
        _falses =  ~(_str_ser.isin(FALSE_SYNONYMS).replace(False, pd.NA)).astype('boolean')
        _combined = _boolean_ser.fillna(_trues).fillna(_falses)    
        df[col] = _combined
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return f"""    TRUE_SYNONYMS = ['true', 'yes', 'on', '1']
    FALSE_SYNONYMS = ['false', 'no', 'off', '0']
    _ser = df['{col}']
    _int_sanitize = _ser.replace(1, True).replace(0, False) 
    _real_bools = _int_sanitize.isin([True, False])
    _boolean_ser = _int_sanitize.where(_real_bools, pd.NA).astype('boolean')    
    _str_ser = _ser.str.lower().str.strip()
    _trues = _str_ser.isin(TRUE_SYNONYMS).replace(False, pd.NA).astype('boolean')
    _falses =  ~ (_str_ser().isin(FALSE_SYNONYMS).replace(False, pd.NA)).astype('boolean')
    _combined = _boolean_ser.fillna(_trues).fillna(_falses)    

    df['{col}'] = _combined"""




class USDate(Command):
    command_default = [s('us_date'), s('df'), "col"]
    command_pattern = []

    @staticmethod 
    def transform(df, col):
        df[col] = pd.to_datetime(df[col], errors='coerce', format="%m/%d/%Y")    
        return df
        
    @staticmethod 
    def transform_to_py(df, col):
        return f"    df['{col}'] = pd.to_datetime(df['{col}'], errors='coerce', format='%m/%d/%Y')"
