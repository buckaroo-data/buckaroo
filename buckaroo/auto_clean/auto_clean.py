import math
import warnings

from collections import defaultdict

import pandas as pd
import numpy as np


#adapted from https://docs.python.org/3/library/warnings.html

# this is needed to see if a series that we think should be datetime
# would throw a warning indicating a slow coercion this saves a huge
# (100x) slowdown

def check_for_datetime_warnings(ser):
    "return 1 if to_datetime throws errors for the series"
    with warnings.catch_warnings(record=True) as w:
        pd.to_datetime(ser, errors='coerce')
        if len(w) == 0:
            return 0
        if "Could not infer format" in str(w[-1].message):
            return 1
        else:
            #not sure how we'd get here
            return 1

default_type_dict = {
    'datetime':0, 'datetime_error':0,
    'int':0, 'int_error':0,
    'float':0, 'float_error':0,
    'bool':0, 'bool_error':0}


#pandas parses ints and floats as datetimes in ns, you end up with a
# lot of values around 1970 Unix epoch we use 1971 as a cutoff, a bit
# of a hack, but pragmatic
SEVENTY_ONE_CUTOFF = pd.to_datetime('1971-01-01')

def get_object_typing_metadata(ser):
    # this function should just return percentages, to separate
    # introspection from action.  This way we can pass in a different
    # decision weighting.  As is this function is complex enough
    counts = defaultdict(lambda: 0)
    counts.update(default_type_dict) # we always want these keys present
    assert pd.api.types.is_object_dtype(ser.dtype)
    #this is slow because it goes through python as opposed to vectorized C code
    for v in ser.values:
        try:
            dt = pd.to_datetime(v)
            if dt > SEVENTY_ONE_CUTOFF:
                counts['datetime'] += 1
            else:
                counts['datetime_error'] += 1
        except (pd.core.tools.datetimes.DateParseError, ValueError, TypeError):
            counts['datetime_error'] += 1

        if isinstance(v, bool):
            counts['bool'] += 1
        else:
            counts['bool_error'] += 1
        if isinstance(v, str):
            try:
                int(v)
                counts['int'] += 1
            except ValueError:
                counts['int_error'] += 1
            try:
                float(v)
                counts['float'] += 1
            except ValueError:
                counts['float_error'] += 1
        elif isinstance(v, float) or isinstance(v, int):
            int(v)
            counts['int'] += 1
            float(v)
            counts['float'] += 1
            
        

    if len(ser) == 0:
        return counts
    ret_dict = dict([[k, v/len(ser)] for k,v in counts.items()])
    
    #this is an ugly hack, but it really speeds things up if there are
    #abberant kind of datetime columns
    if ret_dict['datetime_error'] < .5:
        if check_for_datetime_warnings(ser):
            ret_dict['datetime_error'] = 1.0
    if ret_dict['int_error'] < .5:
        float_remainder = (pd.to_numeric(ser, errors='coerce').abs() % 1).sum()
        if float_remainder > 0.0001:
            ret_dict['int_error'] = 1
    return ret_dict

def get_typing_metadata(ser):
    td = default_type_dict.copy() #type_dict
    dt = ser.dtype
    if not pd.api.types.is_object_dtype(dt):
        td['exact_type'] = str(dt)
        if pd.api.types.is_datetime64_any_dtype(dt):
            #general_type is used as a pass through
            td['general_type'] = 'datetime'
        elif pd.api.types.is_bool_dtype(dt):
            td['general_type'] = 'bool'
        elif pd.api.types.is_categorical_dtype(dt):
            pass #not sure how to handle this yet, it will end up being handled as an object/string
        elif pd.api.types.is_float_dtype(dt):
            #could still be a float that includes only ints
            td['general_type'] = 'float'
            td['float'], td['float_error'] = 1, 0
        elif pd.api.types.is_integer_dtype(dt):
            td['general_type'] = 'int'
            td['int'], td['int_error'] = 1, 0
        return td
    else:
        return get_object_typing_metadata(ser.dropna())

def recommend_type(type_dict):
    if type_dict.get('general_type', None) is not None:
        return type_dict['general_type']
    if type_dict['datetime_error'] < 0.5:
        return 'datetime'
    if type_dict['bool_error'] < 0.5:
        #bool ends up being stricter than int or float
        return 'bool'
    if type_dict['float_error'] < 0.5 or type_dict['int_error'] < 0.5:
        #numeric type, figure out if float or int float will parse for
        # everything that also parses as int
        if math.isclose(type_dict['float'], type_dict['int']) or type_dict['int'] > type_dict['float']:
            return 'int'
        else:
            return 'float'
    return 'string'

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

def emit_command(col_name, new_type):
    # I need a "no-op" new_type that doesn't change a column at all
    # also possible meta tags about commands taht will change data, vs just re-typing
    return [{"symbol":"to_%s" % new_type , "meta":{"precleaning":True}},{"symbol":"df"}, col_name]

def auto_type_df(df):
    #this is much faster because we only run the slow function on a maximum of 200 rows.  
    #That's a good size for an estimate
    sample_size = min(len(df), 200)
    recommended_types = {}
    new_data = {}
    for c in df.columns:
        recommended_types[c] = recommend_type(get_typing_metadata(df[c].sample(sample_size)))
        new_data[c] = coerce_series(df[c], recommended_types[c])
    return pd.DataFrame(new_data)

def get_auto_type_operations(df, metadata_f, recommend_f):
    #this is much faster because we only run the slow function on a maximum of 200 rows.  
    #That's a good size for an estimate
    sample_size = min(len(df), 200)
    cleaning_commands = []
    for c in df.columns:
        metadata = metadata_f(df[c].sample(sample_size))
        new_type = recommend_f(metadata)
        cleaning_commands.append(emit_command(c, new_type))
    return cleaning_commands
