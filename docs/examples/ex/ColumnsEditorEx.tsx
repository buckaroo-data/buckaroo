import React, {useState} from 'react';
import {extraComponents} from 'buckaroo';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';

const sym = extraComponents.utils.sym;
const  {
  symDf,
  CommandConfigT,
  CommandArgSpec
}  = extraComponents.CommandUtils;

export const EmptyDf: DFWhole = {
    dfviewer_config: {
        pinned_rows: [],
        column_config: []
    },
    data: []
};

export const bakedArgSpecs: CommandArgSpec = {
    dropcol: [null],
    fillna: [[3, 'fillVal', 'type', 'integer']],
    remove_outliers: [[3, 'tail', 'type', 'float']],
    search: [[3, 'needle', 'type', 'string']],
    resample: [
        [3, 'frequency', 'enum', ['daily', 'weekly', 'monthly']],
        [4, 'colMap', 'colEnum', ['null', 'sum', 'mean', 'count']]
    ]
};

export const bakedOperationDefaults: OperationDefaultArgs = {
    dropcol: [sym('dropcol'), symDf, 'col'],
    fillna: [sym('fillna'), symDf, 'col', 8],
    remove_outliers: [sym('remove_outliers'), symDf, 'col', 0.02],
    search: [sym('search'), symDf, 'col', 'term'],
    resample: [sym('resample'), symDf, 'col', 'monthly', {}],
};

export const bakedCommandConfig: CommandConfigT = {
    argspecs: bakedArgSpecs,
    defaultArgs: bakedOperationDefaults,
};

export const bakedOperations: Operation[] = [
    [sym('dropcol'), symDf, 'col1'],
    [sym('fillna'), symDf, 'col2', 5],
    [sym('resample'), symDf, 'month', 'monthly', {}],
];

export const dfviewer_config = {
    column_config: [
	{
            col_name: 'index',
            displayer_args: { displayer: 'integer', min_digits: 3, max_digits: 5 },
	},
	{
            col_name: 'svg_column',
            displayer_args: { displayer: 'SVGDisplayer' },
	},
	{
            col_name: 'link_column',
            displayer_args: { displayer: 'linkify' },
	},
	{
            col_name: 'nanObject',
            displayer_args: { displayer: 'integer', min_digits: 3, max_digits: 5 },
            color_map_config: {
		color_rule: 'color_map',
		//map_name: 'DIVERGING_RED_WHITE_BLUE',
		map_name: 'BLUE_TO_YELLOW',
		val_column: 'tripduration',
            },
	}],
    extra_grid_config: { rowHeight: 105 },
    component_config: { height_fraction: 1 },
    pinned_rows: [
	//      { primary_key_val: 'dtype', displayer_args: { displayer: 'obj' } },
	//      {        primary_key_val: 'histogram',        displayer_args: { displayer: 'histogram' },      },
    ]
};


export default  function ColumnsEditorEx() {
    const [operations, setOperations] = useState(bakedOperations);

    const baseOperationResults: OperationResult = {
        transformed_df: EmptyDf,
        generated_py_code: 'default py code',
        transform_error: undefined
    };
    return (
        <extraComponents.ColumnsEditor
        df_viewer_config={dfviewer_config}
        activeColumn={'foo'}
        commandConfig={bakedCommandConfig}
        operations={operations}
        setOperations={setOperations}
        operationResult={baseOperationResults}
            />
    );
}
