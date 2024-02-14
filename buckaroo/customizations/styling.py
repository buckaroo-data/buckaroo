from buckaroo.dataflow.dataflow import StylingAnalysis
from typing import Any

def obj_(pkey):
    return {'primary_key_val': pkey, 'displayer_args': { 'displayer': 'obj' } }

def float_(pkey, digits=3):
    return {'primary_key_val': pkey, 
            'displayer_args': {
                'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}}


class DefaultMainStyling(StylingAnalysis):
    requires_summary = ["histogram", "is_numeric", "dtype", "_type"]
    pinned_rows = [
        obj_('dtype'),
        {'primary_key_val': 'histogram', 'displayer_args': {'displayer': 'histogram'}}]

    @classmethod
    def style_column(kls, col:str, column_metadata: Any) -> Any:
        #print(col, list(sd.keys()))
        if len(column_metadata.keys()) == 0:
            #I'm still having problems with index and polars
            return {'col_name':col, 'displayer_args': {'displayer': 'obj'}}

        digits = 3
        t = column_metadata['_type']
        if t == 'integer':
            disp = {'displayer': 'float', 'min_fraction_digits':0, 'max_fraction_digits':0}
        elif t == 'float':
            disp = {'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}
        elif t == 'temporal':
            disp = {'displayer': 'datetimeLocaleString','locale': 'en-US',  'args': {}}
        elif t == 'string':
            disp = {'displayer': 'string', 'max_length': 35}
        else:
            disp = {'displayer': 'obj'}
        return {'col_name':col, 'displayer_args': disp }


class DefaultSummaryStatsStyling(StylingAnalysis):
    pinned_rows = [
        obj_('dtype'),
        float_('min'),
        float_('mean'),
        float_('max'),
        float_('unique_count', 0),
        float_('distinct_count', 0),
        float_('empty_count', 0)]

    df_display_name = "summary"
    data_key = "empty"
    summary_stats_key= 'all_stats'
