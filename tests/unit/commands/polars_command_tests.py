from collections import OrderedDict
import polars as pl
import numpy as np

from buckaroo.jlisp.lispy import s
from polars.testing import assert_frame_equal
from buckaroo.jlisp.configure_utils import configure_buckaroo
from buckaroo.customizations.polars_commands import (
    DropCol, FillNA, GroupBy #, OneHot, GroupBy, reindex
)


def result_from_exec(code_str, df_input):
    CODE_PREAMBLE = "import polars as pl\nimport numpy as np\n"
    CODE_PREAMBLE += "from buckaroo.auto_clean.auto_clean import smart_to_int\n"
    RETRIEVE_RESULT_STR = '\n__ret_closure[0] = clean(__test_df)'
    outer_scope_result = [0]
    full_code_str = CODE_PREAMBLE + code_str + RETRIEVE_RESULT_STR
    try:
        exec(full_code_str, {'__test_df':df_input, '__ret_closure':outer_scope_result})
    except:
        print("Failure calling exec with following code string")
        print(full_code_str)
    print(full_code_str)
    return outer_scope_result[0]

def assert_to_py_same_transform_df(command_kls, operations, test_df):
    _a, _b, transform_df, transform_to_py = configure_buckaroo([command_kls])
    tdf_ops = [{'symbol': 'begin'}]
    tdf_ops.extend(operations)
    tdf = transform_df(tdf_ops, test_df.clone())
    py_code_string = transform_to_py(operations)

    edf = result_from_exec(py_code_string, test_df.clone())
    assert_frame_equal(tdf, edf)
    return tdf
same = assert_to_py_same_transform_df

def test_fillna():
    base_df = pl.DataFrame({
        'a':[1,2,3,4,5], 'b': [None, 2, 2, 2, None]})
    
    output_df = same(FillNA, [[s('fillna'), s('df'), "b", 100]], base_df)
    assert output_df[0, 'b'] == 100

def test_dropcol():
    base_df = pl.DataFrame({
        'a':np.random.randint(1, 10, 5), 'b':np.random.randint(1, 10, 5),
        'c':np.random.randint(1, 10, 5)})

    same(DropCol, [[s('dropcol'), s('df'), "a"]], base_df)

def test_groupby():
    base_df = pl.DataFrame({
        'a':['cc', 'cc', 'cc', 'ee', 'ff'], 'b': [None, 2, 2, 2, None], 
        'c': [10, 20, 30, 40, 50]})
    
    output_df = same(GroupBy, [[s('groupby'), s('df'), "a", {'b':'count', 'c': 'sum'}]], base_df)
    expected = pl.DataFrame(
        {'a':        ["ff", "ee",  "cc"],
         'b(count)': [   0,    1,    2],
         'c(sum)':   [  50,   40,   60]},
        schema=OrderedDict([('a', pl.Utf8), ('b(count)', pl.UInt32), ('c(sum)', pl.Int64)])
    )
    assert_frame_equal(output_df, expected)


'''


def test_onehot():
    base_df = pd.DataFrame({
        'a':['cc', 'cc', 'dd', 'ee', 'ff'], 'b': [pd.NA, 2, 2, 2, pd.NA]})
    
    output_df = same(OneHot, [[s('onehot'), s('df'), "a"]], base_df)
    assert output_df.columns.to_list() == ['b', 'cc', 'dd', 'ee', 'ff']
    
    
def test_reindex():
    base_df = pd.DataFrame({
        'a':['ca', 'cb', 'cd', 'ee', 'ff'], 'b': [pd.NA, 2, 2, 2, pd.NA]})
    
    output_df = same(reindex, [[s('reindex'), s('df'), "a"]], base_df)
    assert output_df.index.to_list() == ['ca', 'cb', 'cd', 'ee', 'ff']
'''
