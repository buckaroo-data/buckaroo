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

export interface DFColumn {
  name: string;
  type: string;
}
export type DFDataRow = Record<string, string | number | boolean | null>;

export type DFData = DFDataRow[];

export interface ColumnObjHint {
  type: "obj"
  histogram?: any[];
}

export interface ColumnStringHint {
  type: "string";
  histogram?: any[];
}

export interface ColumnBooleanHint {
  type: "boolean";
  histogram?: any[];
}

export interface ColumnIntegertHint {
  type: "integer"
  min_digits: number;
  max_digits: number;
  histogram: any[];
}

export interface ColumnFloatHint {
  type: "float"
  histogram: any[];
}


export type ColumnHint = ColumnObjHint | ColumnIntegertHint | ColumnFloatHint | ColumnStringHint | ColumnBooleanHint;


export interface DFWhole {
  schema: {
    fields: DFColumn[];
    primaryKey: string[]; //['index']
    pandas_version: string; //'1.4.0',
  };
  table_hints: Record<string, ColumnHint>;
  data: DFData;
}

export const EmptyDf: DFWhole = {
  schema: { fields: [], primaryKey: [], pandas_version: '' },
  table_hints: {},
  data: [],
};

//print(sdf.to_json(orient='table', indent=2))

export const histograms = {
  num_histo: [
    { name: '-406 - -332', population: 1 },
    { name: '-332 - -258', population: 0 },
    { name: '-258 - -184', population: 2 },
    { name: '-184 - -111', population: 10 },
    { name: '-111 - -37', population: 22 },
    { name: '-37 - 36', population: 30 },
    { name: '36 - 109', population: 22 },
    { name: '109 - 183', population: 10 },
    { name: '183 - 257', population: 3 },
    { name: '257 - 331', population: 0 },
  ],

  bool_histo: [
    { name: 'False', false: 50 },
    { name: 'True', true: 30 },
    { name: 'NA', NA: 20 },
  ],

  NA_Only: [{ name: 'NA', NA: 100 }],

  simple_catgeorical: [
    { name: 2, cat_pop: 87.0 },
    { name: 1, cat_pop: 13.0 },
  ],

  categorical_histo: [
    { name: 'KTM', cat_pop: 30 },
    { name: 'Gas Gas', cat_pop: 15 },
    { name: 'Yamaha', cat_pop: 10 },
    { name: 'unique', unique: 25 },
    { name: 'NA', NA: 20 },
  ],

  categorical_histo_lt: [
    { name: 'KTM', cat_pop: 25 },
    { name: 'Gas Gas', cat_pop: 12 },
    { name: 'Yamaha', cat_pop: 8 },
    { name: 'NA', NA: 20 },
    { name: 'longtail', unique: 15, longtail: 20 },
  ],

  all_unique: [{ name: 'unique', unique: 100 }],

  unique_na: [
    { name: 'unique', unique: 80 },
    { name: 'NA', NA: 20 },
  ],

  unique_continuous: [
    { name: '-406   -332', population: 1 },
    { name: '-332   -258', population: 0 },
    { name: '-258   -184', population: 0 },
    { name: '-184   -111', population: 10 },
    { name: '-111   -37', population: 21 },
    { name: '-37   36', population: 29 },
    { name: '36   109', population: 22 },
    { name: '109   183', population: 9 },
    { name: '183   257', population: 3 },
    { name: '257   331', population: 0 },
    { name: 'unique', unique: 100 },
  ],

  unique_continuous_scaled: [
    { name: '-406   -332', population: 0 },
    { name: '-332   -258', population: 0 },
    { name: '-258   -184', population: 0 },
    { name: '-184   -111', population: 10 },
    { name: '-111   -37', population: 21 },
    { name: '-37   36', population: 29 },
    { name: '36   109', population: 22 },
    { name: '109   183', population: 9 },
    { name: '183   257', population: 3 },
    { name: '257   331', population: 0 },
    { name: 'unique', unique: 29 },
  ],

  unique_continuous_scaled_50: [
    { name: '-406   -332', population: 0 },
    { name: '-332   -258', population: 0 },
    { name: '-258   -184', population: 0 },
    { name: '-184   -111', population: 10 },
    { name: '-111   -37', population: 21 },
    { name: '-37   36', population: 29 },
    { name: '36   109', population: 22 },
    { name: '109   183', population: 9 },
    { name: '183   257', population: 3 },
    { name: '257   331', population: 0 },
    { name: 'longtail', unique: 15 },
  ],
  start_station_categorical: [
    { name: 'Pershing Square N', cat_pop: 1 },
    { name: '8 Ave & W 31 St', cat_pop: 1 },
    { name: 'Lafayette St & E 8 St', cat_pop: 1 },
    { name: 'W 21 St & 6 Ave', cat_pop: 1 },
    { name: 'E 17 St & Broadway', cat_pop: 1 },
    { name: '8 Ave & W 33 St', cat_pop: 1 },
    { name: 'E 43 St & Vanderbilt Ave', cat_pop: 1 },
    { name: 'unique', cat_pop: 0 },
    { name: 'long_tail', cat_pop: 92 },
    { name: 'NA', cat_pop: 0 },
  ],
};

//export const tableDf2:DFWhole = {
export const foo: DFWhole = {
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
  table_hints: {
    index: {  type:"obj" },
    tripduration: {  histogram: histograms.num_histo, type:"obj"},
    starttime: { type:"obj" },
    stoptime: {  type:"obj" },
    'start station id': {  type:"obj" },
    'start station name': {  type:"obj" },
    'start station latitude': {  type:"obj" },
    bikeid: {  type:"obj" },
    'birth year': {  type:"obj" },
    gender: {  type:"obj" },
  },
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
  schema: {
    fields: [
      { name: 'index', type: 'integer' },
      { name: 'nanNumeric', type: 'int' },
      { name: 'nanObject', type: 'int' },
      { name: 'nanFloat', type: 'float' },
      { name: 'end station name', type: 'string' },
      { name: 'tripduration', type: 'integer' },
      { name: 'start station name', type: 'string' },
      { name: 'floatCol', type: 'float' },
    ],
    primaryKey: ['index'],
    pandas_version: '1.4.0',
  },
  data: [
    {
      index: 0,
      'end station name': 'Elizabeth St & Hester St',
      tripduration: 471,
      'start station name': 'Catherine St & Monroe St',
      floatCol: '1.111',
      nanNumeric: null,
      nanObject: null,
      nanFloat: null,
    },
    {
      index: 1,
      'end station name': 'South St & Whitehall St',
      tripduration: 1494,
      'start station name': '1 Ave & E 30 St',
      floatCol: '8.888',
      nanNumeric: null,
      nanObject: null,
      nanFloat: null,
    },
    {
      index: 2,
      'end station name': 'E 59 St & Sutton Pl',
      tripduration: 464,
      'start station name': 'E 48 St & 3 Ave',
      floatCol: '9.999',
      nanNumeric: null,
      nanObject: null,
      nanFloat: null,
    },
    {
      index: 3,
      'end station name': 'E 33 St & 5 Ave',
      tripduration: 373,
      'start station name': 'Pershing Square N',
      floatCol: '-10.1',
      nanCol: null,
      nanNumeric: null,
      nanObject: null,
      nanFloat: null,
    },
    {
      index: 4,
      'end station name': 'Hancock St & Bedford Ave',
      tripduration: 660,
      'start station name': 'Atlantic Ave & Fort Greene Pl',
      floatCol: '10.99',
      nanNumeric: null,
      nanObject: null,
      nanFloat: null,
    },
  ],
  table_hints: {
    'end station name': {
      
      histogram: histograms.categorical_histo_lt,
      type:"obj" },
    
    tripduration: {
      type:"integer",      
      min_digits: 3,
      max_digits: 4,
      histogram: histograms.num_histo,
    },
    'start station name': {
      
      histogram: histograms.bool_histo,
      type:"string" },
    floatCol: {
      type:"float",
      
      histogram: [
        { name: 521, cat_pop: 0.0103 },
        { name: 358, cat_pop: 0.0096 },
        { name: 519, cat_pop: 0.009 },
        { name: 497, cat_pop: 0.0087 },
        { name: 293, cat_pop: 0.0082 },
        { name: 285, cat_pop: 0.0081 },
        { name: 435, cat_pop: 0.008 },
        { name: 'unique', cat_pop: 0.0001 },
        { name: 'long_tail', cat_pop: 0.938 },
        { name: 'NA', cat_pop: 0.0 },
      ],
    },
    nanNumeric: {
      type: "integer", 
      min_digits: 1,
      max_digits: 3,
      histogram: histograms.num_histo,
    },
    nanFloat: {
      type:"float",
      histogram: histograms.num_histo,
    },
    nanObject: {
      
      type:"obj"
    },
  },
};

export const stringIndexDf: DFWhole ={
  schema: {
    fields: [
      {name: 'index', type:'integer'},
      {name: 'a', type:'integer'},
      {name: 'b', type:'boolean'},
      {name: 'strings', type:'boolean'}],
    primaryKey: ['index'],
    pandas_version: '1.4.0',
  },
  data: [{index: 0, a: 1, b: true,   strings:"a", },
	 {index: 1, a: 2, b: false,  strings:"", },
	 {index: 2, a: 3, b: false,  strings:" ", }],
  table_hints: {
    a: {type:"integer",
      min_digits: 1,
      max_digits: 1,
  
  	histogram: [{name: 1, cat_pop: 50.0},
		      {name: 2, cat_pop: 50.0},
		      {name: 'longtail', unique: 100.0}]},
    b: {type:"integer",
	min_digits: 1,
	max_digits: 1,
	histogram: [{name: true, cat_pop: 50.0},
		    {name: false, cat_pop: 50.0},
		    {name: 'longtail', unique: 100.0}]},
    strings: {type:"string",
	      histogram: []}
  }}
