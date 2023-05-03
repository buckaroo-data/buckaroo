from .lispy import s
from .configure_utils import configure_buckaroo
import pandas as pd
import numpy as np

class Command(object):
    pass
    
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

class DropCol(Command):
    #argument_names = ["df", "col"]
    command_default = [s('dropcol'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        df.drop(col, axis=1, inplace=True)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df.drop('%s', axis=1, inplace=True)" % col

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
            "    df.drop('%s', inplace=True)" % (col),
            "    df = df.join(one_hot)"]
        return "\n".join(commands)

group_df = pd.DataFrame({'a':[10,20,30,40,50,60],
                   'b':[1,2,3,4,5,6],
                   'c':['q', 'q', 'q', 'q', 'w', 'w']})

def safe_int(x):
    try:
        return int(x)
    except:
        return np.nan

class SafeInt(Command):
    command_default = [s('safeint'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        df[col] = df[col].apply(safe_int)
        #df[col] = 5
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = df['%s'].apply(safe_int)" % (col, col)


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

    test_df = group_df
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
    


class to_datetime(Command):
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

DefaultCommandKlsList = [DropCol, to_datetime, SafeInt, FillNA, reindex, OneHot, GroupBy]
command_defaults, command_patterns, buckaroo_transform, buckaroo_to_py_core = configure_buckaroo(DefaultCommandKlsList)

