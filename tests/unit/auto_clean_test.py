
import pandas as pd
from buckaroo.auto_clean import auto_clean as ac
from pandas import NA as NA
from numpy import nan
from pandas.testing import assert_series_equal


DATETIME_META = {'datetime': 0.75, 'datetime_error': 0.25, 'int': 0.25, 'int_error': 0.75, 'float': 0.25, 'float_error': 0.75, 'bool': 0, 'bool_error':1}

INT_META = {'datetime': 0.0, 'datetime_error': 1.0, 'int': 0.75, 'int_error': 0.25, 'float': 0.75, 'float_error': 0.25, 'bool': 0.0, 'bool_error': 1.0}

FULL_INT_META = {'datetime': 0.0, 'datetime_error': 0, 'int': 1, 'int_error': 0, 'float': 0, 'float_error': 0, 'bool': 0.0, 'bool_error': 0, 'exact_type': 'UInt32', 'general_type':'int'}

FLOAT_META = {'datetime': 0.0, 'datetime_error': 1.0, 'int': 0.25, 'int_error': 0.75, 'float': 0.75, 'float_error': 0.25, 'bool': 0.0, 'bool_error': 1.0}

STRING_META =  {'datetime': 0.0, 'datetime_error': 1.0, 'int': 0.0, 'int_error': 1.0, 'float': 0.25, 'float_error': 0.75, 'bool': 0.0, 'bool_error': 1.0}

DATETIME_EDGECASE_META = {'datetime': 1.0, 'datetime_error': 1.0, 'int': 0.0, 'int_error': 1.0, 'float': 0.0, 'float_error': 1, 'bool': 0.0, 'bool_error': 1.0}

BOOL_META = {'bool': .6, 'bool_error': 0.4,
             'datetime': 0.0, 'datetime_error': 1.0,
             'float': 0.6, 'float_error': 0.4,
             'int': 0.6, 'int_error': 0.4}


MIXED_NUMERIC_META = {'bool': 0.0, 'bool_error': 1.0,
                      'datetime': 0.0, 'datetime_error': 1.0,
                      'float': (2/3), 'float_error': (1/3),
                      'int': (2/3), 'int_error': (1/3)}

def assign_values(d, new_values):
    d2 = d.copy()
    d2.update(new_values)
    return d2

DATETIME_DTYPE_META = assign_values(ac.default_type_dict,
                                    {'general_type':'datetime', 'exact_type': 'datetime64[ns]'})

MIXED_EXACT = assign_values(ac.default_type_dict, {'exact_type': 'Int64', 'general_type': 'int', 'int':1})

ONLY_NANS_META = {'datetime': 0, 'datetime_error': 0, 'int': 0, 'int_error': 0, 'float': 0, 'float_error': 0, 'bool': 0, 'bool_error': 0}

# WEIRD_INT = {'bool': 0.0, 'bool_error': 1.0,
#                       'datetime': 0.0, 'datetime_error': 1.0,
#                       'float': (2/3), 'float_error': (1/3),
#                       'int': (2/3), 'int_error': (1/3)}


def test_get_typing_metadata():
    if int(pd.__version__[0]) < 2:
        return

    # In pandas 3.0+, string Series have a 'str' dtype rather than 'object',
    # so force object dtype to test the object type path
    def obj_series(data):
        """Create an object-dtype series for testing the object typing path."""
        return pd.Series(data, dtype='object')

    # assert WEIRD_INT == ac.get_typing_metadata(pd.Series([5, 2, 3.1, None, NA]))
    assert INT_META == ac.get_typing_metadata(obj_series(['181', '182', '183', 'a']))
    assert FLOAT_META == ac.get_typing_metadata(obj_series(['181.1', '182.2', '183', 'a']))
    assert STRING_META == ac.get_typing_metadata(obj_series(['181.1', 'b', 'c', 'a']))
    assert DATETIME_META == ac.get_typing_metadata(obj_series(['1981-05-11', '1982-05-11', '1983', 'a']))
    assert DATETIME_EDGECASE_META == ac.get_typing_metadata(obj_series(['00:01.6', '00:01.6', '00:01.6', None]))

    # datetime dtype metadata - handle both ns and us resolution
    dt_meta = ac.get_typing_metadata(pd.date_range('2010-01-01', '2010-01-31'))
    assert dt_meta['general_type'] == 'datetime'
    assert 'datetime64' in dt_meta['exact_type']

    assert MIXED_EXACT == ac.get_typing_metadata(pd.Series([NA, 2, 3, NA, NA], dtype='Int64'))
    assert MIXED_NUMERIC_META == ac.get_typing_metadata(obj_series(['a', 2.0, 3.0, None, NA]))

    #there are still problems here, the code isn't properly distinguishing bools from ints and bools
    assert BOOL_META == ac.get_typing_metadata(obj_series(['a', 'b', False, True, False]))
    assert FULL_INT_META == ac.get_typing_metadata(pd.Series([5]*10, dtype='UInt32'))

    # what does the typing code do on "dtype" objects
    ac.get_typing_metadata(pd.Series([pd.Series([5], dtype='UInt32').dtype]*3))



    #only nans
    assert ac.get_typing_metadata(pd.Series([None])) == ONLY_NANS_META
    assert ac.get_typing_metadata(pd.Series([NA, NA])) == ONLY_NANS_META
    assert ac.get_typing_metadata(pd.Series([])) == ONLY_NANS_META
    assert ac.get_typing_metadata(pd.Series([nan, NA])) == ONLY_NANS_META
    #assert ac.get_typing_metadata(pd.Series([nan, nan])) == ONLY_NANS_META

def test_recommend_type():
    assert ac.recommend_type(DATETIME_META) == 'datetime'
    assert ac.recommend_type(INT_META) == 'int'
    assert ac.recommend_type(FLOAT_META) == 'float'
    assert ac.recommend_type(STRING_META) == 'string'
    assert ac.recommend_type(DATETIME_DTYPE_META) == 'datetime'

    WEIRD_INT_SER = pd.Series(['a', 2, 3, 4, None])
    assert ac.recommend_type( ac.get_typing_metadata(WEIRD_INT_SER)) == 'int'

def test_smart_to_int():
    assert_series_equal(
        ac.smart_to_int(pd.Series(['a', 2, 3, 4, None])),
        pd.Series([NA, 2,3,4, NA], dtype='UInt8'))


    # this should throw an error
    # assert_series_equal(
    #     ac.smart_to_int(pd.Series(['a', 2.0, 3.1, None, NA])),
    #     pd.Series([NA, 2,3,4, NA], dtype='UInt8'))


def test_coerce_series():
    assert_series_equal(
        ac.coerce_series(pd.Series(['a', 2, 3, 4, None]), 'int'),
        pd.Series([NA, 2,3,4, NA], dtype='UInt8'))

    assert_series_equal(
        ac.coerce_series(pd.Series(['a', False, True, None]), 'bool'),
        pd.Series([NA, False, True, NA], dtype='boolean'))

    assert_series_equal(
        ac.coerce_series(pd.Series(['a', 2.0, 3.0, None, NA]), 'int'),
        pd.Series([NA, 2, 3, NA, NA], dtype='UInt8'))

    assert_series_equal(
        ac.coerce_series(pd.Series(['a', 2.0, 3.1, None, NA]), 'float'),
        pd.Series([nan, 2, 3.1, nan, nan], dtype='float'))
