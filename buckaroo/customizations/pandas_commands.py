import pandas as pd
import numpy as np

from ..jlisp.lispy import s

class Command(object):
    @staticmethod 
    def transform(df, col, val):
        return df

    @staticmethod 
    def transform_to_py(df, col, val):
        return "    # no op  df['%s'].fillna(%r)" % (col, val)

class NoOp(Command):
    #used for testing command stuff
    command_default = [s('noop'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    #noop"

class FillNA(Command):
    #argument_names = ["df", "col", "fill_val"]
    command_default = [s('fillna'), s('df'), "col", 8]
    command_pattern = [[3, 'fillVal', 'type', 'integer']]

    @staticmethod 
    def transform(df, col, val):
        df.fillna({col:val}, inplace=True)
        return df

    @staticmethod 
    def transform_to_py(df, col, val):
        return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)

class OneHot(Command):
    command_default = [s('onehot'), s('df'), "col"]
    command_pattern = [None]
    @staticmethod 
    def transform(df, col):
        one_hot = pd.get_dummies(df[col])
        df.drop(col, axis=1, inplace=True)
        #how to make this inplace?
        return df.join(one_hot) 

    @staticmethod 
    def transform_to_py(df, col):
        commands = [
            "    one_hot = pd.get_dummies(df['%s'])" % (col),
            "    df.drop('%s', axis=1, inplace=True)" % (col),
            "    df = df.join(one_hot)"]
        return "\n".join(commands)


def smart_to_int(ser):

    if pd.api.types.is_numeric_dtype(ser):
        working_ser = ser
        lower, upper = ser.min(), ser.max()
    else:
        working_ser = pd.to_numeric(ser, errors='coerce')
        lower, upper = working_ser.min(), working_ser.max()


    if lower < 0:
        if upper < np.iinfo(np.int8).max:
            new_type = 'Int8'
        elif upper < np.iinfo(np.int16).max:
            new_type = 'Int16'
        elif upper < np.iinfo(np.int32).max:
            new_type = 'Int32'
        else:
            new_type = 'Int64'
    else:
        if upper < np.iinfo(np.uint8).max:
            new_type = 'UInt8'
        elif upper < np.iinfo(np.uint16).max:
            new_type = 'UInt16'
        elif upper < np.iinfo(np.uint32).max:
            new_type = 'UInt32'
        else:
            new_type = 'UInt64'
    base_ser = pd.to_numeric(ser, errors='coerce').dropna()
    return base_ser.astype(new_type).reindex(ser.index)

def coerce_series(ser, new_type):
    if new_type == 'bool':
        #dropna is key here, otherwise Nan's and errors are treated as true
        return pd.to_numeric(ser, errors='coerce').dropna().astype('boolean').reindex(ser.index)
    elif new_type == 'datetime':
        return pd.to_datetime(ser, errors='coerce').reindex(ser.index)
    elif new_type == 'int':
        # try:
            return smart_to_int(ser)
        # except:
        #     #just let pandas figure it out, we recommended the wrong type
        #     return pd.to_numeric(ser, errors='coerce')
        
    elif new_type == 'float':
        return pd.to_numeric(ser, errors='coerce').dropna().astype('float').reindex(ser.index)
    elif new_type == 'string':
        if int(pd.__version__[0]) < 2:
            return ser.fillna(value="").astype('string').reindex(ser.index)
        return ser.fillna(value="").astype('string').replace("", None).reindex(ser.index)
    else:
        raise Exception("Unkown type of %s" % new_type)



class SafeInt(Command):
    command_default = [s('safe_int'), s('df'), "col"]
    command_pattern = [None]


    @staticmethod 
    def transform(df, col):
        if col == 'index':
            return df
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

class RemoveOutliers(Command):
    command_default = [s('remove_outliers'), s('df'), "col", 1]
    #command_pattern = [[3, 'remove_outliers_99', 'type', 'float']]
    command_pattern = [[3, 'remove_outliers', 'type', 'integer']]


    @staticmethod 
    def transform(df, col, int_tail):
        if col == 'index':
            return df
        ser = df[col]
        tail = int_tail / 100
        new_df = df[(ser > np.quantile(ser, tail)) & (ser < np.quantile(ser, 1-tail ))]
        print("pre_filter", len(df), "post_filter", len(new_df))
        return new_df

    @staticmethod 
    def transform_to_py(df, col, int_tail):
        C = f"df['{col}']"
        tail = int_tail / 100
        low_tail = tail
        high_tail = 1-tail
        return f"    df[({C} > np.quantile({C}, {low_tail})) & ({C} < np.quantile({C}, {high_tail}))]" 


class OnlyOutliers(Command):
    command_default = [s('only_outliers'), s('df'), "col", 1]
    #command_pattern = [[3, 'remove_outliers_99', 'type', 'float']]
    command_pattern = [[3, 'only_outliers', 'type', 'integer']]


    @staticmethod 
    def transform(df, col, int_tail):
        if col == 'index':
            return df
        ser = df[col]
        tail = int_tail / 100
        new_df = df[(ser < np.quantile(ser, tail)) | (ser > np.quantile(ser, 1-tail ))]
        print("pre_filter", len(df), "post_filter", len(new_df))
        return new_df

    @staticmethod 
    def transform_to_py(df, col, int_tail):
        C = f"df['{col}']"
        tail = int_tail / 100
        low_tail = tail
        high_tail = 1-tail
        return f"    df[({C} < np.quantile({C}, {low_tail})) | ({C} > np.quantile({C}, {high_tail}))]" 



class GroupBy(Command):
    command_default = [s("groupby"), s('df'), 'col', {}]
    command_pattern = [[3, 'colMap', 'colEnum', ['null', 'sum', 'mean', 'median', 'count']]]
    @staticmethod 
    def transform(df, col, col_spec):
        grps = df.groupby(col)
        df_contents = {}
        for k, v in col_spec.items():
            if v == "sum":
                df_contents[k] = grps[k].apply(lambda x: x.sum())
            elif v == "mean":
                df_contents[k] = grps[k].apply(lambda x: x.mean())
            elif v == "median":
                df_contents[k] = grps[k].apply(lambda x: x.median())
            elif v == "count":
                df_contents[k] = grps[k].apply(lambda x: x.count())
        return pd.DataFrame(df_contents)

    #test_df = group_df
    test_sequence = [s("groupby"), s('df'), 'c', dict(a='sum', b='mean')]
    test_output = pd.DataFrame(
        {'a':[100, 110], 'b':[2.5, 5.5]},
        index=['q','w'])

    @staticmethod 
    def transform_to_py(df, col, col_spec):
        commands = [
            "    grps = df.groupby('%s')" % col,
            "    df_contents = {}"
        ]
        for k, v in col_spec.items():
            if v == "sum":
                commands.append("    df_contents['%s'] = grps['%s'].apply(lambda x: x.sum())" % (k, k))
            elif v == "mean":
                commands.append("    df_contents['%s'] = grps['%s'].apply(lambda x: x.mean())" % (k, k))
            elif v == "median":
                commands.append("    df_contents['%s'] = grps['%s'].apply(lambda x: x.median())" % (k, k))
            elif v == "count":
                commands.append("    df_contents['%s'] = grps['%s'].apply(lambda x: x.count())" % (k, k))
        #print("commands", commands)
        commands.append("    df = pd.DataFrame(df_contents)")
        return "\n".join(commands)



class DropCol(Command):
    #argument_names = ["df", "col"]
    command_default = [s('dropcol'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        df.drop(col, axis=1, inplace=True)
        print("dropcol.transform")
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df.drop('%s', axis=1, inplace=True)" % col



class ato_datetime(Command):
    #argument_names = ["df", "col"]
    command_default = [s('to_datetime'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        df[col] = pd.to_datetime(df[col])
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = pd.to_datetime(df['%s'])" % (col, col)    

class reindex(Command):
    command_default = [s('reindex'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        old_col = df[col]
        df.drop(col, axis=1, inplace=True)
        df.index = old_col.values
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "\n".join(
            ["    old_col = df['%s']" % col,
             "    df.drop('%s', axis=1, inplace=True)" % col,
             "    df.index = old_col.values"])

def search_df_str(df, needle:str):
    existing_bool = pd.Series(False, index=np.arange(len(df)), dtype='boolean')
    str_cols = list(df.select_dtypes("string").columns)
    str_cols.extend(list(df.select_dtypes("object").columns))
    for col in str_cols:
        bool_result = ~(df[col].str.find(needle).fillna(-1) == -1).fillna(False)
        existing_bool = existing_bool | bool_result
    return df[existing_bool]    



class Search(Command):
    #argument_names = ["df", "col", "fill_val"]
    command_default = [s('Search'), s('df'), "col", ""]
    command_pattern = [[3, 'term', 'type', 'string']]

    @staticmethod 
    def transform(df, col, val):
        
        print("search_df", val)
        if val is None or val == "":
            print("no search term set")
            return df
        return search_df_str(df, val)


    @staticmethod 
    def transform_to_py(df, col, val):
        return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)
