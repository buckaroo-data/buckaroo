import pandas as pd
import numpy as np


from ..jlisp.lisp_utils import s

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

class MakeCategory(Command):
    command_default = [s('make_category'), s('df'), "col"]
    command_pattern = [None]


    @staticmethod 
    def transform(df, col):
        if col == 'index':
            return df
        # maybe check for str or int
        df[col] = df[col].astype('category')
        return df


    @staticmethod 
    def transform_to_py(df, col):
        return f"    df['{col}'] = df['{col}'].astype('category')"

class RemoveOutliers(Command):
    command_default = [s('remove_outliers'), s('df'), "col", .01]
    #command_pattern = [[3, 'remove_outliers_99', 'type', 'float']]
    command_pattern = [[3, 'remove_outliers', 'type', 'float']]


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
    command_default = [s('only_outliers'), s('df'), "col", .01]
    command_pattern = [[3, 'only_outliers', 'type', 'float']]
    quick_args_pattern = [[2, 'term', 'type', 'col']]

    @staticmethod 
    def transform(df, col, tail):
        if col == 'index':
            return df
        ser = df[col]
        if(pd.api.types.is_integer_dtype(ser)):
            mean = int(ser.mean())
        else:
            mean = ser.mean()
        f_ser = ser.fillna(mean) # fill_series don't care about null rows, fill with mean
        
        new_df = df[(f_ser < np.quantile(f_ser, tail)) | (f_ser > np.quantile(f_ser, 1-tail ))]

        return new_df

    @staticmethod 
    def transform_to_py(df, col, tail):
        C = f"df['{col}']"
        high_tail = 1-tail
        
        py_lines = [f"    if(pd.api.types.is_integer_dtype({C})):",
                    f"        mean = int({C}.mean())",
                    "    else:",
                    f"        mean = {C}.mean()",
                    f"    f_ser = {C}.fillna(mean)  # fill series with mean",
                    f"    df = df[(f_ser < np.quantile(f_ser, {tail})) | (f_ser > np.quantile(f_ser, {high_tail} ))]"]
        return "\n".join(py_lines)

class LinearRegression(Command):


    command_default = [s("linear_regression"), s('df'), 'col', {}]
    command_pattern = [[3, 'x_cols', 'colEnum', ['null', 'basic', 'one_hot']]]
    @staticmethod 
    def transform(df, col, col_spec):
        from sklearn.linear_model import LinearRegression
        # Evaluate the model
        #r2_score = model.score(x, y)
        #print(f"R-squared value: {r2_score}")

        all_cols = [col] # include y
        x_cols = [] 
        for k, v in col_spec.items():
            if v == "null":
                continue
            elif v == "basic":
                all_cols.append(k)
                x_cols.append(k)
            elif v == "one_hot":
                #do one hot stuff
                pass
        pdf = df[all_cols].dropna(axis=0)
        
        model = LinearRegression()
        model.fit(pdf[x_cols], pdf[col])


        prediction = model.predict(pdf[x_cols])
        pdf['predicted'] = prediction
        pdf['err'] = pdf['predicted'] - pdf[col]


        existing_cols = list(df.columns)
        existing_cols.remove(col)
        df[col + '_predicted'] = pdf['predicted']
        df[col + '_pred_err'] = pdf['err']
        
        new_cols = [col, col + '_predicted', col + '_pred_err']
        new_cols.extend(existing_cols)
        return df[new_cols].copy()

    @staticmethod 
    def transform_to_py(df, col, col_spec):

        commands = [
            "    from sklearn.linear_model import LinearRegression",
            f"    all_cols = ['{col}'] # include y",
            "    x_cols = []"]
        for k, v in col_spec.items():
            if v == "null":
                continue
            elif v == "basic":
                commands.append(f"    all_cols.append('{k}')")
                commands.append(f"    x_cols.append('{k}')")
            elif v == "one_hot":
                #do one hot stuff
                pass

        pred_col = col+"_predicted"
        pred_err_col = col+"_pred_err"
        commands.extend([
            "    pdf = df[all_cols].dropna(axis=0)",
            "    model = LinearRegression()",
            f"    model.fit(pdf[x_cols], pdf['{col}'])",
            "    ",
            "    prediction = model.predict(pdf[x_cols])",
            "    pdf['predicted'] = prediction",
            f"    pdf['err'] = pdf['predicted'] - pdf['{col}']",

            f"    df['{pred_col}'] = pdf['predicted']",
            f"    df['{pred_err_col}'] = pdf['err']"])
        return "\n".join(commands)



AGG_METHODS_WITH_HELP = [  # ordered in aproximate frequency of use
('null', "Don't aggregate this column"),
('mean', 'Return the mean value.'),
('median', 'Return the median value.'),
('min', 'Return the minimum value.'),
('max', 'Return the maximum value.'),
('sum', 'Return the sum of the series.'),
('count', 'Returns count of non-missing values.'),
('count_null', 'Returns count of missing values.'),
('std', 'Return the standard deviation of the data.'),

('empty', "True if no values in series."),
('hasnans' 'True if missing values in series.'),
('nunique', 'Return the count of unique values.'),


('is_monotonic', 'True if values always increase.'),
('is_monotonic_decreasing', 'True if values always decrease.'),
('is_monotonic_increasing', 'True if values always increase.'),


('all', 'Returns True if every value is truthy.'),
('any', 'Returns True if any value is truthy.'),

('autocorr', 'Returns Pearson correlation of series with shifted self. Can override lag as keyword argument(default is 1).'),

('kurt', 'Return ”excess” kurtosis (0 is normal distribution). Values greater than 0 have more outliers than normal.'),
('mad', 'Return the mean absolute deviation.'),

('sem', 'Return the unbiased standard error.'),
('skew', 'Return the unbiased skew of the data. Negative indicates tail is on the left side.'),

('idxmax' "Returns index value of maximum value."),
('idxmin', 'Returns index value of minimum value.'),

('dtype', 'Type of the series.'),
('dtypes', 'Type of the series.'),
('nbytes', 'Return the number of bytes of the data.'),
('ndim', 'Return the number of dimensions (1) of the data.'),
('size', 'Return the size of the data.'),
# These aggregations exist, but need an extra argument
#('cov', 'Return covariance of series with other series. Need to specify other.'),
#('corr', 'Returns Pearson correlation of series with other series. Need to specify other.'),
#('quantile', 'Return the median value. Can override q to specify other quantile.'),
]


AGG_METHOD_NAMES = [x[0] for x in AGG_METHODS_WITH_HELP]

class GroupBy(Command):
    command_default = [s("groupby"), s('df'), 'col', {}]
    command_pattern = [[3, 'colMap', 'colEnum', AGG_METHOD_NAMES]]
    @staticmethod 
    def transform(df, col, col_spec):
        grps = df.groupby(col)
        df_contents = {}
        for k, v in col_spec.items():
            if v == "null":
                continue
            elif v == 'count_null':
                df_contents[k] = grps[k].agg('size') - grps[k].agg('count')
            else:
                df_contents[k] = grps[k].agg(v)
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
            if v == "null":
                continue
            elif v == 'count_null':
                commands.append(f"    df_contents['{k}'] = grps['{k}'].agg('size') - grps['{k}'].agg('count') #count_null")
            else:
                commands.append(f"    df_contents['{k}'] = grps['{k}'].agg('{v}')")
        commands.append("    df = pd.DataFrame(df_contents)")
        return "\n".join(commands)

class GroupByTransform(Command):
    command_default = [s("groupby_transform"), s('df'), 'col', {}]
    command_pattern = [[3, 'colMap', 'colEnum', AGG_METHOD_NAMES]]



    @staticmethod 
    def transform(df, col, col_spec):
        grps = df.groupby(col)
        for k, v in col_spec.items():
            new_col_name = k + "_" + v
            if v == "null":
                continue
            elif v == 'count_null':
                df[new_col_name] = grps[k].transform('size') - grps[k].transform('count')
            else:
                df[new_col_name] = grps[k].transform(v)
        return df


    @staticmethod 
    def transform_to_py(df, col, col_spec):
        commands = [
            f"    grps = df.groupby('{col}')"
        ]
        for k, v in col_spec.items():
            new_col_name = k + "_" + v
            if v == "null":
                continue
            elif v == 'count_null':
                commands.append(f"    df['{new_col_name}'] = grps['{k}'].agg('size') - grps['{k}'].agg('count') #count_null")
            else:
                commands.append(f"    df['{new_col_name}'] = grps['{k}'].agg('{v}')")
        return "\n".join(commands)


class DropCol(Command):
    command_default = [s('dropcol'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        df.drop(col, axis=1, inplace=True)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df.drop('%s', axis=1, inplace=True)" % col



class ato_datetime(Command):
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
    command_default = [s('search'), s('df'), "col", ""]
    command_pattern = [[3, 'term', 'type', 'string']]
    quick_args_pattern = [[3, 'term', 'type', 'string']]

    @staticmethod 
    def transform(df, col, val):
        #print("search_df", val)
        if val is None or val == "":
            #print("no search term set")
            return df
        return search_df_str(df, val)


    @staticmethod 
    def transform_to_py(df, col, val):
        return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)


def search_col_str(df, col, needle:str):
    existing_bool = pd.Series(False, index=np.arange(len(df)), dtype='boolean')
    str_cols = [col]
    for col in str_cols:
        bool_result = ~(df[col].str.find(needle).fillna(-1) == -1).fillna(False)
        existing_bool = existing_bool | bool_result
    return df[existing_bool]    


class SearchCol(Command):
    command_default = [s('search_col'), s('df'), "col", ""]
    command_pattern = [[3, 'term', 'type', 'string']]

    @staticmethod 
    def transform(df, col, val):
        
        #print("search_df", val)
        if val is None or val == "":
            #print("no search term set")
            return df
        return search_col_str(df, col, val)


    @staticmethod 
    def transform_to_py(df, col, needle):
        return f"    df = df[~(df['{col}'].str.find('{needle}').fillna(-1) == -1).fillna(False)]"



class DropDuplicates(Command):
    command_default = [s("drop_duplicates"), s('df'), 'col', "first"]
    command_pattern = [[3, 'keep', 'enum', ["first", "last", "False"]]]
    

    @staticmethod 
    def transform(df, col, val):
        if val == "False":
            return df[col].drop_duplicates(keep=False)
        else:
            return df[col].drop_duplicates(keep=val)


    @staticmethod 
    def transform_to_py(df, col, val):
        if val == "False":
            keep_arg = "False"
        else:
            keep_arg = f"'{val}'"
        return f"    df = df['{col}'].drop_duplicates(keep={keep_arg})"

class Rank(Command):
    command_default = [s("rank"), s('df'), 'col', "None", False]
    command_pattern = [[3, 'method', 'enum', ["None", "min", "dense"]],
                       [4, 'new_col', 'bool']
                       ]
    

    @staticmethod 
    def transform(df, col, method, new_col):
        arg_values = {"None":None, "min":"min", "dense":"dense"}
        method_arg = arg_values[method]
        if new_col:
            new_col_name = f"{col}_rank"
            assert new_col_name not in df.columns
            df[new_col_name] = df[col].rank(method=method_arg)
            return df
        else:
            df[col] = df[col].rank(method=method_arg)
            return df

    @staticmethod 
    def transform_to_py(df, col, val, new_col):
        arg_values = {"None":'None', "min":"'min'", "dense":"'dense'"}
        method_arg = arg_values[val]
        if new_col:
            new_col_name = f"{col}_rank"
            return f"    df = df['{col}'].rank(method={method_arg})"
        else:
            return f"    df = df['{new_col_name}'].rank(method={method_arg})"


                       

class Replace(Command):
    command_default = [s("replace"), s('df'), 'col', "", ""]
    command_pattern = [[3, 'old', 'type', 'string'],
                       [4, 'new_', 'type', 'string']
                       ]

    @staticmethod 
    def transform(df, col, prev, new_):
        df[col] = df[col].replace(prev, new_)
        return df

    @staticmethod 
    def transform_to_py(df, col, prev, new_):
        return f"    df['{col}'] = df['{col}'].replace('{prev}', '{new_}')"

# string commands to add
#split
# age = pd.Series(['0-10', '11-15', '11-15', '61-65', '46-50'])
# (age
# .str.split('-', expand=True) .iloc[:,0]
# .astype(int)
# )


