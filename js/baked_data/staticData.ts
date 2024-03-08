import { OperationDefaultArgs, Operation } from '../components/OperationUtils';
import { sym } from '../components/utils';
import {
  symDf,
  CommandConfigT,
  bakedArgSpecs,
} from '../components/CommandUtils';
import {
  DFData,
  DFViewerConfig,
  DFWhole,
} from '../components/DFViewerParts/DFWhole';

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

export const smileyPNGString =
  'iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURBVEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kovIHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00YFsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvPFxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQbqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96CutRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFthatyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlithJtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosXVTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCDV1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wbwLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjLYCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII=';

//export const tableDf2:DFWhole = {
export const foo: DFWhole = {
  dfviewer_config: {
    column_config: [
      { col_name: 'index', displayer_args: { displayer: 'obj' } },

      { col_name: 'tripduration', displayer_args: { displayer: 'obj' } },
      { col_name: 'starttime', displayer_args: { displayer: 'obj' } },
      { col_name: 'stoptime', displayer_args: { displayer: 'obj' } },
      { col_name: 'start station id', displayer_args: { displayer: 'obj' } },
      { col_name: 'start station name', displayer_args: { displayer: 'obj' } },
      {
        col_name: 'start station lattitude',
        displayer_args: { displayer: 'obj' },
      },
      { col_name: 'bikeid', displayer_args: { displayer: 'obj' } },
      { col_name: 'birth year', displayer_args: { displayer: 'obj' } },
      { col_name: 'gender', displayer_args: { displayer: 'obj' } },
    ],
    pinned_rows: [],
  },

  //    index: { type: 'obj' },
  //    tripduration: { histogram: histograms.num_histo, type: 'obj' },
  /*
    starttime: { type: 'obj' },
    stoptime: { type: 'obj' },
    'start station id': { type: 'obj' },
    'start station name': { type: 'obj' },
    'start station latitude': { type: 'obj' },
    bikeid: { type: 'obj' },
    'birth year': { type: 'obj' },
    gender: { type: 'obj' },
    */
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
      img_: smileyPNGString,
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
export const stringIndexDf = foo;

export const tableDf: DFWhole = {
  dfviewer_config: {
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
      },
      {
        col_name: 'nanFloat',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8,
        },
        tooltip_config: { tooltip_type: 'summary_series' },
      },
      { col_name: 'end station name', displayer_args: { displayer: 'obj' } },
      {
        col_name: 'tripduration',
        displayer_args: { displayer: 'integer', min_digits: 1, max_digits: 5 },
        color_map_config: {
          color_rule: 'color_map',
          map_name: 'BLUE_TO_YELLOW',
        },
      },
      {
        col_name: 'start station name',
        displayer_args: { displayer: 'obj' },
        color_map_config: {
          color_rule: 'color_not_null',
          conditional_color: 'red',
          exist_column: 'nanFloat',
        },
      },
      {
        col_name: 'floatCol',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 1,
          max_fraction_digits: 3,
        },
      },
      {
        col_name: 'nanNumeric',
        displayer_args: { displayer: 'integer', min_digits: 3, max_digits: 5 },
        tooltip_config: {
          tooltip_type: 'simple',
          val_column: 'start station name',
        },
      },
      {
        col_name: 'img_',
        displayer_args: { displayer: 'Base64PNGImageDisplayer' },
        ag_grid_specs: { width: 150 },
      },
    ],
    extra_grid_config: { rowHeight: 105 },
    component_config: { height_fraction: 1 },
    pinned_rows: [
      //      { primary_key_val: 'dtype', displayer_args: { displayer: 'obj' } },
      //      {        primary_key_val: 'histogram',        displayer_args: { displayer: 'histogram' },      },
    ],
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
      //svg_column: '<h1> paddy </h1>',
      link_column: 'https://buckaroo.dev',
      img_: smileyPNGString,
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
      svg_column:
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100" viewBox="43.4952 4.7852 4.449600000000004 3.3796" preserveAspectRatio="xMinYMin meet"><g transform="matrix(1,0,0,-1,0,12.95)"><path fill-rule="evenodd" fill="#66cc99" stroke="#555555" stroke-width="0.08899200000000007" opacity="0.6" d="M 47.78,8.0 L 44.96,5.0 L 43.66,4.95 L 46.94,7.99 L 47.78,8.0 z" /></g></svg>',
      link_column: 'https://pola.rs/',
    },
    {
      index: 2,
      'end station name': 'E 59 St & Sutton Pl',
      tripduration: 464,
      'start station name': 'E 48 St & 3 Ave',
      floatCol: '9.999',
      nanNumeric: null,
      nanObject: null,
      svg_column:
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100.0" height="100.0" viewBox="29.0828 3.4328 1.8143999999999991 1.2343999999999995" preserveAspectRatio="xMinYMin meet"><g transform="matrix(1,0,0,-1,0,8.1)"><path fill-rule="evenodd" fill="#66cc99" stroke="#555555" stroke-width="0.03628799999999998" opacity="0.6" d="M 30.83,3.5 L 29.95,4.17 L 29.71,4.6 L 29.15,4.38 L 30.83,3.5 z" /></g></svg>',
      nanFloat: 10,
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
      svg_column:
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100.0" height="100.0" viewBox="40.693599999999996 -1.9163999999999999 1.6728000000000094 6.3828" preserveAspectRatio="xMinYMin meet"><g transform="matrix(1,0,0,-1,0,2.5500000000000003)"><path fill-rule="evenodd" fill="#66cc99" stroke="#555555" stroke-width="0.127656" opacity="0.6" d="M 41.58,-1.68 L 40.93,-0.85 L 40.95,2.78 L 41.85,3.91 L 42.13,4.23 L 41.58,-1.68 z" /></g></svg>',
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
      nanFloat: 3,
    },
  ],
};

export const dfviewer_config_no_pinned: DFViewerConfig = {
  column_config: tableDf.dfviewer_config.column_config,
  pinned_rows: [
    { primary_key_val: 'dtype', displayer_args: { displayer: 'obj' } },
    {
      primary_key_val: 'histogram',
      displayer_args: { displayer: 'histogram' },
    },
  ],
};
const tripDurationBins = [0, 300, 500, 1000, 1500];

export const summaryDfForTableDf: DFData = [
  {
    index: 'histogram',
    'end station name': histograms.categorical_histo_lt,
    tripduration: histograms.num_histo,
    'start station name': histograms.bool_histo,
    nanNumeric: histograms.num_histo,
    nanFloat: histograms.num_histo,
    nanObject: histograms.num_histo,
    floatCol: [
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
  {
    index: 'histogram_bins',
    tripduration: tripDurationBins,
    nanObject: tripDurationBins,
  },
  {
    index: 'dtype',
    'end station name': 'String6666',
    tripduration: 'object',
    'start station name': 'object',
    nanNumeric: 'float64',
    nanFloat: 'flot64',
    nanObject: 'object',
    floatCol: 'float',
  },
];

export const realSummaryTableData: DFData = [
  { index: 'dtype', int_col: 'int64', float_col: 'float64', str_col: 'object' },
  { index: 'min', int_col: 1, float_col: 1.4285714286 },
  { index: 'max', int_col: 49, float_col: 41.4285714286, str_col: null },
  { index: 'mean', int_col: 24.75, float_col: 22.4714285714 },
  { index: 'unique_count', int_col: 4, float_col: 0, str_col: 0 },
  { index: 'empty_count', int_col: 0, float_col: 0, str_col: 0 },
  { index: 'distinct_count', int_col: 49, float_col: 29, str_col: 1 },
];

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
    //  {'col_name': 'index',  'displayer_args': {'displayer': 'string'}},
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
