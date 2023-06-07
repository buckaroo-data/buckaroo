import { OperationDefaultArgs, Operation } from './OperationUtils';
import { sym } from './utils';
import { symDf, CommandConfigT, bakedArgSpecs } from './CommandUtils';

export const bakedOperationDefaults: OperationDefaultArgs = {
  dropcol: [sym('dropcol'), symDf, 'col'],
  fillna: [sym('fillna'), symDf, 'col', 8],
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
/*
const origColumns = [
  { key: 'id', name: 'ID' },
  { key: 'title', name: 'Title' },
];

const origRows = [
  { id: 0, title: 'Example' },
  { id: 1, title: 'Demo' },
];
*/
export interface DFColumn {
  name: string; type:string;
}
export type DFDataRow = Record<string, string | number | boolean>;

export type DFData = DFDataRow[];

export interface ColumnObjHint {
  is_numeric:false;
}

export interface ColumnNumHint {
  is_numeric:true;
  is_integer:boolean;
  min_digits:number;
  max_digits:number;
  histogram:number[][];
}

export type ColumnHint = ColumnObjHint | ColumnNumHint
export interface DFWhole {
  schema: {
    fields: DFColumn[];
    primaryKey: string[]; //['index']
    pandas_version: string; //'1.4.0',


  };
  table_hints:Record<string, ColumnHint>;
  data: DFData;
}

export const EmptyDf: DFWhole = {
  schema: { fields: [], primaryKey:[], pandas_version:"" },
  table_hints:{},
  data: [],
};

//print(sdf.to_json(orient='table', indent=2))

//export const tableDf2:DFWhole = {
export const foo:DFWhole = {

  schema: {
    fields: [
      { name: 'index', type: 'integer' },
      { name: 'tripduration', type: 'integer' },
      { name: 'starttime', type: 'string' },
      { name: 'stoptime', type: 'string' },
      { name: 'start station id', type: 'integer' },
      { name: 'start station name', type: 'string' },
      { name: 'start station latitude', type: 'number' },
      { name: 'bikeid', type: 'integer' },
      { name: 'birth year', type: 'string' },
      { name: 'gender', type: 'integer' },
    ],

    primaryKey: ['index'],
    pandas_version: '1.4.0',
  },
  table_hints: { 'index': { is_numeric:false},
		 'tripduration': { is_numeric:false},
		 'starttime': { is_numeric:false},
		 'stoptime': { is_numeric:false},
		 'start station id': { is_numeric:false},
		 'start station name': { is_numeric:false},
		 'start station latitude': { is_numeric:false},
		 'bikeid': { is_numeric:false},
		 'birth year': { is_numeric:false},
		 'gender': { is_numeric:false}},
  data: [
    {
      index: 0,
      tripduration: 404,
      starttime: '2014-07-01 00:00:04',
      stoptime: '2014-07-01 00:06:48',
      'start station id': 545,
      'start station name': 'E 23 St & 1 Ave',
      'start station latitude': 40.736502,
      bikeid: 19578,
      'birth year': '1987',
      gender: 2,
    },
    {
      index: 1,
      tripduration: 850,
      starttime: '2014-07-01 00:00:06',
      stoptime: '2014-07-01 00:14:16',
      'start station id': 238,
      'start station name': 'Bank St & Washington St',
      'start station latitude': 40.7361967,
      bikeid: 19224,
      'birth year': '1987',
      gender: 1,
    },
    {
      index: 2,
      tripduration: 1550,
      starttime: '2014-07-01 00:00:21',
      stoptime: '2014-07-01 00:26:11',
      'start station id': 223,
      'start station name': 'W 13 St & 7 Ave',
      'start station latitude': 40.73781509,
      bikeid: 17627,
      'birth year': '1973',
      gender: 2,
    },
    {
      index: 3,
      tripduration: 397,
      starttime: '2014-07-01 00:00:29',
      stoptime: '2014-07-01 00:07:06',
      'start station id': 224,
      'start station name': 'Spruce St & Nassau St',
      'start station latitude': 40.71146364,
      bikeid: 15304,
      'birth year': '1982',
      gender: 1,
    },
    {
      index: 4,
      tripduration: 609,
      starttime: '2014-07-01 00:00:37',
      stoptime: '2014-07-01 00:10:46',
      'start station id': 346,
      'start station name': 'Bank St & Hudson St',
      'start station latitude': 40.73652889,
      bikeid: 20062,
      'birth year': '1972',
      gender: 2,
    },
  ],
};

export const tableDf: DFWhole = {
  'schema': {'fields': [
    {'name': 'index', 'type': 'integer'},
    {'name': 'end station name', 'type': 'string'},
    {'name': 'tripduration', 'type': 'integer'},
    {'name': 'start station name', 'type': 'string'},
    {'name': 'floatCol', 'type': 'float'}
  ],
	     'primaryKey': ['index'],
	     'pandas_version': '1.4.0'},
  'data': [{'index': 0,
	    'end station name': 'Elizabeth St & Hester St',
	    'tripduration': 471,
	    'start station name': 'Catherine St & Monroe St',
	    'floatCol': '1.111',
	   }

	   ,
	   {'index': 1,
	    'end station name': 'South St & Whitehall St',
	    'tripduration': 1494,
	    'start station name': '1 Ave & E 30 St',
	    'floatCol': '8.888'
	   },
	   {'index': 2,
	    'end station name': 'E 59 St & Sutton Pl',
	    'tripduration': 464,
	    'start station name': 'E 48 St & 3 Ave',
	    'floatCol': '9.999'
	   },
	   {'index': 3,
	    'end station name': 'E 33 St & 5 Ave',
	    'tripduration': 373,
	    'start station name': 'Pershing Square N',
	    'floatCol': '-10.1'
	   },
	   {'index': 4,
	    'end station name': 'Hancock St & Bedford Ave',
	    'tripduration': 660,
	    'start station name': 'Atlantic Ave & Fort Greene Pl',
	    'floatCol': '10.99'
	   }],
  'table_hints':
  {
    'end station name': {'is_numeric': false},
    'tripduration': {'is_numeric': true,
		     'is_integer': true,
		     'min_digits': 3,
		     'max_digits': 4,
		     'histogram': [[0.6, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
				   [373.0, 485.1, 597.2, 709.3, 821.4, 933.5, 1045.6,
				    1157.7, 1269.8, 1381.9, 1494.0]]},
    'start station name': {'is_numeric': false},
    'floatCol': {'is_numeric': true,
		 'is_integer': false,
		     'min_digits': 1,
		     'max_digits': 3,
		     'histogram': [[0.6, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
				   [373.0, 485.1, 597.2, 709.3, 821.4, 933.5, 1045.6,
				    1157.7, 1269.8, 1381.9, 1494.0]]},
  }}
