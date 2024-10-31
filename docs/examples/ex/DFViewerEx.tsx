import React, {useState} from 'react';
import {extraComponents} from 'buckaroo';
export const smileyPNGString =
  'iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURBVEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kovIHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00YFsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvPFxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQbqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96CutRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFthatyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlithJtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosXVTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCDV1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wbwLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjLYCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII=';

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
const histograms = {
    CategoricalUniqueNA: [
        {name: 'KTM', cat_pop: 30},
        {name: 'Gas Gas', cat_pop: 15},
        {name: 'Yamaha', cat_pop: 10},
        {name: 'unique', unique: 25},
        {name: 'NA', NA: 20}
    ],
    Numeric: [
        {name: '-406 - -332', population: 1},
        {name: '-332 - -258', population: 0},
        {name: '-258 - -184', population: 2},
        {name: '-184 - -111', population: 10},
        {name: '-111 - -37', population: 22},
        {name: '-37 - 36', population: 30},
        {name: '36 - 109', population: 22},
        {name: '109 - 183', population: 10},
        {name: '183 - 257', population: 3},
        {name: '257 - 331', population: 0}
    ],
    BoolWithNA: [
        {name: 'False', false: 50},
        {name: 'True', true: 30},
        {name: 'NA', NA: 20}
    ]
}

const tripDurationBins = [0, 300, 500, 1000, 1500];
export const summaryDfForTableDf: DFData = [
  {
    index: 'histogram',
      'end station name': histograms.CategoricalUniqueNA,
      tripduration: histograms.Numeric,
      'start station name': histograms.BoolWithNA,
    nanNumeric: histograms.Numeric,
    nanFloat: histograms.Numeric,
    nanObject: histograms.Numeric,
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


export default function DFViewerEx() {
    const [activeCol, setActiveCol] = useState('tripduration');
    return (
        <extraComponents.DFViewer
            df_data={tableDf.data}
            df_viewer_config={tableDf.dfviewer_config}
            summary_stats_data={summaryDfForTableDf}
            activeCol={activeCol}
            setActiveCol={setActiveCol}
        />
    );
}
