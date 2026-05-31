import re
import pandas as pd
import numpy as np

from buckaroo.pluggable_analysis_framework.utils import cache_series_func


# I don't want to apply these caching functions more generally because
# I'm worried about putting a large object inot the cache results.
# Since these return scalars, it's fairly cheap, and these functions
# are specifically slow , I"m fine with it

# importantly these functions are run interactively, so speed is important

@cache_series_func
def regular_int_parse_frac(ser):
    null_count = (~ser.apply(pd.to_numeric, errors="coerce").isnull()).sum()
    return null_count / len(ser)


digits_and_period = re.compile(r"[^\d\.]")

@cache_series_func
def strip_int_parse_frac(ser):
    if pd.api.types.is_object_dtype(ser):
        ser = ser.astype("string")
    if not pd.api.types.is_string_dtype(ser):
        return 0
    ser = ser.sample(np.min([300, len(ser)]))
    stripped = ser.str.replace(digits_and_period, "", regex=True)

    # don't like the string conversion here, should still be vectorized
    int_parsable = ser.astype(str).str.isdigit()
    parsable = int_parsable | (stripped != "")
    return parsable.sum() / len(ser)


TRUE_SYNONYMS = ["true", "yes", "on", "1"]
FALSE_SYNONYMS = ["false", "no", "off", "0"]
BOOL_SYNONYMS = TRUE_SYNONYMS + FALSE_SYNONYMS

@cache_series_func
def str_bool_frac(ser):
    ser = ser.sample(np.min([300, len(ser)]))
    if pd.api.types.is_object_dtype(ser):
        ser = ser.astype("string")
    if not pd.api.types.is_string_dtype(ser):
        return 0
    matches = ser.str.lower().str.strip().isin(BOOL_SYNONYMS)
    return matches.sum() / len(ser)

@cache_series_func
def us_dates_frac(ser):
    parsed_dates = pd.to_datetime(ser, errors="coerce", format="%m/%d/%Y")
    return (~parsed_dates.isna()).sum() / len(ser)

@cache_series_func
def euro_dates_frac(ser):
    parsed_dates = pd.to_datetime(ser, errors="coerce", format="%d/%m/%Y")
    return (~parsed_dates.isna()).sum() / len(ser)
