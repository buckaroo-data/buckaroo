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
        base_config = {'col_name':str(col)}
        if t == 'integer':
            disp = {'displayer': 'float', 'min_fraction_digits':0, 'max_fraction_digits':0}
        elif t == 'float':
            disp = {'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}
        elif t == 'datetime':
            disp = {'displayer': 'datetimeLocaleString','locale': 'en-US',  'args': {}}
        elif t == 'string':
            disp = {'displayer': 'string', 'max_length': 35}
            base_config['tooltip_config'] = {'tooltip_type':'simple', 'val_column': str(col)}
        else:
            disp = {'displayer': 'obj'}
            base_config['tooltip_config'] = {'tooltip_type':'simple', 'val_column': str(col)}
        base_config['displayer_args'] = disp 
        return base_config


class DefaultSummaryStatsStyling(StylingAnalysis):
    requires_summary = [
        "dtype", "non_null_count", "null_count", "unique_count", "distinct_count",
        "mean", "std", "min", 
        "median",
        "max",
        "most_freq", "2nd_freq", "3rd_freq", "4th_freq", "5th_freq"]
    pinned_rows = [
        obj_('dtype'),
        float_('non_null_count', 0),
        float_('null_count', 0),
        float_('unique_count', 0),
        float_('distinct_count', 0),
        float_('mean'),
        float_('std'),
        float_('min'),
        float_('median'),
        float_('max'),
        obj_('most_freq'),
        obj_('2nd_freq'),
        obj_('3rd_freq'),
        obj_('4th_freq'),
        obj_('5th_freq')
    ]

    df_display_name = "summary"
    data_key = "empty"
    summary_stats_key= 'all_stats'
