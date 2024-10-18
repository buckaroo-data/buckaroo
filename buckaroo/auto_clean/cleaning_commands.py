from ..jlisp.lisp_utils import s
from ..jlisp.configure_utils import configure_buckaroo
from .auto_clean import smart_to_int, get_auto_type_operations
import pandas as pd

class Command(object):
    pass

class to_bool(Command):
    #argument_names = ["df", "col"]
    command_default = [s('to_bool'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        ser = df[col]
        df[col] = pd.to_numeric(ser, errors='coerce').dropna().astype('boolean').reindex(ser.index)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = pd.to_numeric(df['%s'], errors='coerce').dropna().astype('boolean').reindex(df['%s'].index)" % (col, col, col)

class to_datetime(Command):
    #argument_names = ["df", "col"]
    command_default = [s('to_datetime'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        ser = df[col]
        df[col] =  pd.to_datetime(ser, errors='coerce').reindex(ser.index)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = pd.to_datetime(df['%s'], errors='coerce').reindex(df['%s'].index)" % (col, col, col)

class to_int(Command):
    #argument_names = ["df", "col"]
    command_default = [s('to_int'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        ser = df[col]
        try:
            df[col] = smart_to_int(ser)
        except Exception:
            #just let pandas figure it out, we recommended the wrong type
            df[col] = pd.to_numeric(ser, errors='coerce')

        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = smart_to_int(df['%s'])" % (col, col)

class to_float(Command):
    #argument_names = ["df", "col"]
    command_default = [s('to_float'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        ser = df[col]
        df[col] = pd.to_numeric(ser, errors='coerce').dropna().astype('float').reindex(ser.index)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = pd.to_numeric(df['%s'], errors='coerce')" % (col, col)

class to_string(Command):
    #argument_names = ["df", "col"]
    command_default = [s('to_string'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        ser = df[col]
        if int(pd.__version__[0]) < 2:
            df[col] = ser.fillna(value="").astype('string').reindex(ser.index)
            return df
        df[col] = ser.fillna(value="").astype('string').replace("", None).reindex(ser.index)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = df['%s'].fillna(value='').astype('string').replace('', None)" % (col, col)



cleaning_classes = [to_bool, to_datetime, to_int, to_float, to_string,]

def auto_type_df2(df):
    _command_defaults, _command_patterns, transform, buckaroo_to_py_core = configure_buckaroo(
            cleaning_classes)

    cleaning_operations = get_auto_type_operations(df)

    full_ops  = [{'symbol': 'begin'}]
    full_ops.extend(cleaning_operations)
    return transform(full_ops, df)
