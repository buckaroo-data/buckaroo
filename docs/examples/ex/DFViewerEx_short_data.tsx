import React, {useState} from 'react';
import {extraComponents} from 'buckaroo';
export const realSummaryConfig: DFViewerConfig = {
	pinned_rows: [
	    { primary_key_val: 'dtype', displayer_args: { displayer: 'obj' } },
	    {
		primary_key_val: 'min',
		displayer_args: {
		    displayer: 'float',
		    min_fraction_digits: 3,
		    max_fraction_digits: 3,
		},
	    },
	    {
		primary_key_val: 'mean',
		displayer_args: {
		    displayer: 'float',
		    min_fraction_digits: 3,
		    max_fraction_digits: 3,
		},
	    },
	    {
		primary_key_val: 'max',
		displayer_args: {
		    displayer: 'float',
		    min_fraction_digits: 3,
		    max_fraction_digits: 3,
		},
	    },
	    {
		primary_key_val: 'unique_count',
		displayer_args: {
		    displayer: 'float',
		    min_fraction_digits: 0,
		    max_fraction_digits: 0,
		},
	    },
	    {
		primary_key_val: 'distinct_count',
		displayer_args: {
		    displayer: 'float',
		    min_fraction_digits: 0,
		    max_fraction_digits: 0,
		},
	    },
	    {
		primary_key_val: 'empty_count',
		displayer_args: {
		    displayer: 'float',
		    min_fraction_digits: 0,
		    max_fraction_digits: 0,
		},
	    },
	],
	column_config: [
	    {
		col_name: 'index',
		displayer_args: { displayer: 'string' },
		ag_grid_specs: { minWidth: 150, pinned: 'left' },
	    },
	    { col_name: 'int_col', displayer_args: { displayer: 'obj' } },
	    { col_name: 'float_col', displayer_args: { displayer: 'obj' } },
	    { col_name: 'str_col', displayer_args: { displayer: 'obj' } },
	],
    };

export const realSummaryTableData: DFData = [
	{ index: 'dtype', int_col: 'int64', float_col: 'float64', str_col: 'object' },
	{ index: 'min', int_col: 1, float_col: 1.4285714286 },
	{ index: 'max', int_col: 49, float_col: 41.4285714286, str_col: null },
	{ index: 'mean', int_col: 24.75, float_col: 22.4714285714 },
	{ index: 'unique_count', int_col: 4, float_col: 0, str_col: 0 },
	{ index: 'empty_count', int_col: 0, float_col: 0, str_col: 0 },
	{ index: 'distinct_count', int_col: 49, float_col: 29, str_col: 1 },
    ];


export default function DFViewerExString() {

    const [activeCol, setActiveCol] = useState('tripduration');
    const dfv_config: any = {
        column_config: realSummaryConfig.column_config,
        pinned_rows: []
    };

    return (
        <extraComponents.DFViewer
        df_data={realSummaryTableData.slice(0, 3)}
        df_viewer_config={dfv_config}
        summary_stats_data={[]}
        activeCol={activeCol}
        setActiveCol={setActiveCol}
            />
    );
}
