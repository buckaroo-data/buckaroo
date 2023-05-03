import pandas as pd
import numpy as np
from .lispy import make_interpreter, s
import json

def dropcol(df, col):
    df.drop(col, axis=1, inplace=True)
    return df

def fillna(df, col, val):
    df.fillna({col:val}, inplace=True)
    return df


sample_df = pd.DataFrame({'a':[2,None], 'b':['3', 'a'], 'c':[5, None]})

def test_dropcol():
    dropped_df = dropcol(sample_df.copy(), 'b')
    assert dropped_df is not sample_df
    #I want to make sure we haven't modified df
    assert len(dropped_df.columns) != len(sample_df.columns)
    assert 'b' not in dropped_df.columns


def test_fillna():
    filled_df = fillna(sample_df.copy(), 'a', 13)

    assert filled_df is not sample_df
    assert np.isnan(sample_df.iloc[1]['a'])
    assert np.isnan(sample_df.iloc[1]['c'])
    assert np.isnan(filled_df.iloc[1]['c'])
    assert filled_df.iloc[1]['a'] == 13


_eval, raw_parse = make_interpreter({'dropcol':dropcol, 'fillna':fillna})
def dcf_transform(instructions, df):
    df_copy = df.copy()
    return _eval(instructions, {'df':df_copy})

def test_interpret_fillna():
    # I would like to have symbol:df be implicit,  I can do that later
    filled_df = dcf_transform(
         [s('fillna'), s('df'), 'a', 13], sample_df)
    assert filled_df is not sample_df
    assert np.isnan(sample_df.iloc[1]['a'])
    assert np.isnan(sample_df.iloc[1]['c'])
    assert np.isnan(filled_df.iloc[1]['c'])
    assert filled_df.iloc[1]['a'] == 13

                              
def test_interpret_dropcol():
    # I would like to have symbol:df be implicit,  I can do that later
    dropped_df = dcf_transform(
        [s('dropcol'), s('df'), 'b'], sample_df)
    assert dropped_df is not sample_df
    #I want to make sure we haven't modified df
    assert len(dropped_df.columns) != len(sample_df.columns)
    assert 'b' not in dropped_df.columns

def test_interpret_multiple_dropcol():
    # I would like to have symbol:df be implicit,  I can do that later
    dropped_df = dcf_transform([
        s('begin'), 
        [s('dropcol'), s('df'), 'b'],
        [s('dropcol'), s('df'), 'c']],
                               sample_df)


    # [
    #     {"symbol":"begin"},[[{"symbol":"dropcol"},{"symbol":"df"},"tripduration"]]]
    assert dropped_df is not sample_df
    #I want to make sure we haven't modified df
    assert len(dropped_df.columns) != len(sample_df.columns)
    assert 'b' not in dropped_df.columns
    assert 'c' not in dropped_df.columns


print(json.dumps([s('dropcol'), s('df'), 'b']))

    
def dropcol_py(df, col):
    return "    df.drop('%s', axis=1, inplace=True)" % col

def fillna_py(df, col, val):
    return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)


_convert_to_python, _convert_to_py_lisp = make_interpreter({'dropcol':dropcol_py, 'fillna':fillna_py})

def dcf_to_py(instructions):
    #I would prefer to implement this with a macro named something
    #like 'clean' that is implemented for the _convert_to_python
    #interpreter to return a string code block, and for the real DCF
    #interpreter as 'begin'... that way the exact same instructions
    #could be sent to either interpreter.  For now, this will do
    individual_instructions =  [x for x in map(lambda x:_convert_to_python(x, {'df':5}), instructions)]
    code_block =  '\n'.join(individual_instructions)

    return "def clean(df):\n" + code_block

expected_py_output = """def clean(df):
    df.drop('b', axis=1, inplace=True)
    df.drop('c', axis=1, inplace=True)"""

def test_to_py():
    assert dcf_to_py([[s('dropcol'), s('df'), 'b'],
                      [s('dropcol'), s('df'), 'c']]) == expected_py_output
    assert dcf_to_py(
        [
            [{'symbol': 'dropcol'}, {'symbol': 'df'}, 'starttime'],
            [{'symbol': 'dropcol'}, {'symbol': 'df'}, 'stoptime']])== "asdf"



def fillna(df, col, val):
    df.fillna({col:val}, inplace=True)
    return df

def fillna_py(df, col, val):
    return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)


class Arguments(object):

    df = "df"
    column_name = "column_name"
    of_type = "of_type"

class TransformType(object):

    column = "column"
    multi_column = "multi_column"
    shape_change = "shape_change"

class Transform(object):

    t_type = TransformType.column
    transform = fillna
    transform_to_py = fillna_py

    argument_types = [Arguments.df, Arguments.column_name, Arguments.of_type]
    argument_names = ["df", "col", "val"]
    command_template = [s('fillna'), s('df'), "col", "val"]
    

class FillNA(Transform):
    t_type = TransformType.column

    @staticmethod 
    def transform(df, col, val):
        df.fillna({col:val}, inplace=True)
        return df

    @staticmethod 
    def transform_to_py(df, col, val):
        return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)

    arguments = [Arguments.df, Arguments.column_name, Arguments.of_type]
    argument_names = ["df", "col", "val"]
    command_template = [s('fillna'), s('df'), "col", "val"]


class OneHot(Transform):
    t_type = TransformType.column

    @staticmethod 
    def transform(df, col, val):
        one_hot = pd.get_dummies(df[col])
        df = df.drop(col, axis=1, inplace=True)
        #how to make this inplace?
        return df.join(one_hot) 


    @staticmethod 
    def transform_to_py(df, col, val):
        commands = [
            "    one_hot = pd.get_dummies(df['%s'])" % (col),
            "    df.drop('%s', inplace=True)" % (col),
            "    df = df.join(one_hot)"]
        return "\n".join(commands)

    arguments = [Arguments.df, Arguments.column_name, Arguments.of_type]
    
    

