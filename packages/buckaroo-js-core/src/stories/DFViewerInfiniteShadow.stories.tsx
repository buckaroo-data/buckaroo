import type { Meta, StoryObj } from "@storybook/react";
import { DatasourceWrapper, DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { SetColumFunc } from "../components/DFViewerParts/gridUtils";

import { IDatasource, IGetRowsParams } from "@ag-grid-community/core";
import _ from "lodash";
import { ShadowDomWrapper } from "./StoryUtils";

const DFViewerInfiniteWrap = ({
    data,
    df_viewer_config,
    summary_stats_data,
    activeCol,
    setActiveCol,
    outside_df_params,
    error_info,
}: {
    data: DFData;
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: DFData;
    activeCol?: string;
    setActiveCol?: SetColumFunc;
    // these are the parameters that could affect the table,
    // dfviewer doesn't need to understand them, but it does need to use
    // them as keys to get updated data
    outside_df_params?: any;
    error_info?: string;
}) => {

  const tempDataSource:IDatasource = {
    rowCount:data.length,
    getRows(params:IGetRowsParams) {
      const slicedData = data.slice(params.startRow, params.endRow);
      params.successCallback(slicedData, data.length)

    }
  };
  const data_wrapper:DatasourceWrapper = {
    datasource:tempDataSource,
    data_type:"DataSource",
    length:data.length
  }
  return (
    <ShadowDomWrapper>
     <div style={{height:500, width:800}}>
      <DFViewerInfinite
      data_wrapper={data_wrapper}
      df_viewer_config={df_viewer_config}
      summary_stats_data={summary_stats_data}
      activeCol={activeCol}
      setActiveCol={setActiveCol}
      outside_df_params={outside_df_params}
      error_info={error_info} />
     </div>
     </ShadowDomWrapper>);
}

    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/DFViewerInfiniteShadow",
  component:DFViewerInfiniteWrap,
  parameters: {
    // Optional parameter to center the component in the Canvas. More
    // info: https://storybook.js.org/docs/configure/story-layout
    layout: "centered",
      
  },
  // This component will have an automatically generated Autodocs
  // entry: https://storybook.js.org/docs/writing-docs/autodocs
  tags: ["autodocs"],
  // More on argTypes: https://storybook.js.org/docs/api/argtypes
  argTypes: {
      //backgroundColor: { control: "color" },
      //operations: 
  },
  // Use `fn` to spy on the onClick arg, which will appear in the
  // actions panel once invoked:
  // https://storybook.js.org/docs/essentials/actions#action-args
  //args: { onClick: fn() },
} satisfies Meta<typeof DFViewerInfiniteWrap>;

export default meta;
type Story = StoryObj<typeof meta>;
const data = [
    {'a':20, 'b':"foo"},
    {'a':30, 'b':"bar"},
    {'a':NaN, 'b':NaN},
    {'a':null, 'b':null},
    {'a':undefined, 'b':undefined}

  ];

export const Primary: Story = {
  args: {
    //@ts-ignore
    // the undefineds aren't allowed in the type but do happen in the wild
    data:data,
    df_viewer_config: {
      column_config: [
      {
        col_name: 'a',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8,
        },
        //tooltip_config: { tooltip_type: 'summary_series' },
      },
      {
        col_name: 'a',
        displayer_args: {
          displayer: 'integer',
          min_digits:2, max_digits:3
        },
      },
      {
        col_name: 'b',
        displayer_args: {
          displayer: 'obj',
        },
      },
      {
        col_name: 'b',
        displayer_args: {
          displayer: 'string',
        },
      }
    ],
    pinned_rows:[]
  },
  
    }
}

const dictOfArraystoDFData = (dict:Record<string, any[]>):DFData => {
  const keys = _.keys(dict);
  const length = dict[keys[0]].length;

  return _.times(length, index => {
    return _.reduce(keys, (result, key) => {
        //@ts-ignore
        result[key] = dict[key][index];
        return result;
      }, {});
  });
}

const arange = (N:number):number[] => {
  const retArr:number[] = [];
  for(var i =0; i< N; i++){
    retArr.push(i)
  }
  return retArr
}
const NRandom = (N:number, low:number, high:number):number[] => {
  const retArr:number[] = [];
  for(var i =0; i< N; i++){
    retArr.push(Math.floor((Math.random() * (high-low))+low))
  }
  return retArr
}

const N = 10_000;
console.log("156")
console.log(dictOfArraystoDFData({'a':NRandom(N, 3,50), 'b':arange(N)   }))

export const Large: Story = {
  args: {
    data:dictOfArraystoDFData({'a':NRandom(N, 3,50), 'b':arange(N)   }),
    df_viewer_config: {
      column_config: [
      {
        col_name: 'a',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8,
        },
        //tooltip_config: { tooltip_type: 'summary_series' },
      },
      {
        col_name: 'a',
        displayer_args: {
          displayer: 'integer',
          min_digits:2, max_digits:3
        },
      },
      {
        col_name: 'b',
        displayer_args: {
          displayer: 'obj',
        },
      },
    ],
    pinned_rows:[]
  },
  
    }
}


export const PinnedRows: Story = {
  args: {
    data: [], //dictOfArraystoDFData({'a':NRandom(N, 3,50), 'b':arange(N)   }),
    df_viewer_config: {
      column_config: [

        {
          col_name: 'a',
          displayer_args: {
            displayer: 'obj',
          },
        },
        {
          col_name: 'b',
          displayer_args: {
            displayer: 'obj',
          },
        },
        {
          col_name: 'c',
          displayer_args: {
            displayer: 'obj',
          },
        },
        {
          col_name: 'd',
          displayer_args: {
            displayer: 'obj',
          },
        },
      ],
      pinned_rows: [{
        'primary_key_val': 'histogram',
        'displayer_args': { 'displayer': 'histogram' }
      }]
    },
    summary_stats_data: [{
      'index': 'histogram',
      'a': [{ 'name': 'np.int64(35) - 39.0', 'tail': 1 },
      { 'name': '40-68', 'population': 29.0 },
      { 'name': '68-96', 'population': 16.0 },
      { 'name': '96-125', 'population': 14.0 },
      { 'name': '125-153', 'population': 11.0 },
      { 'name': '153-181', 'population': 10.0 },
      { 'name': '181-209', 'population': 8.0 },
      { 'name': '209-237', 'population': 5.0 },
      { 'name': '237-266', 'population': 3.0 },
      { 'name': '266-294', 'population': 2.0 },
      { 'name': '294-322', 'population': 2.0 },
      { 'name': '323.1500000000001 - np.int64(373)', 'tail': 1 }],
      'b': [{ 'name': 'np.int64(0) - 0.0', 'tail': 1 },
      { 'name': '2-4', 'population': 10.0 },
      { 'name': '4-6', 'population': 10.0 },
      { 'name': '6-7', 'population': 10.0 },
      { 'name': '7-9', 'population': 10.0 },
      { 'name': '9-11', 'population': 10.0 },
      { 'name': '11-13', 'population': 10.0 },
      { 'name': '13-15', 'population': 10.0 },
      { 'name': '15-16', 'population': 10.0 },
      { 'name': '16-18', 'population': 10.0 },
      { 'name': '18-20', 'population': 10.0 },
      { 'name': '21.0 - np.int64(21)', 'tail': 1 }],
      'c': [{ 'name': 'np.int64(1) - 1.0', 'tail': 1 },
      { 'name': '2-7', 'population': 11.0 },
      { 'name': '7-11', 'population': 11.0 },
      { 'name': '11-16', 'population': 9.0 },
      { 'name': '16-21', 'population': 7.0 },
      { 'name': '21-26', 'population': 11.0 },
      { 'name': '26-30', 'population': 11.0 },
      { 'name': '30-35', 'population': 9.0 },
      { 'name': '35-40', 'population': 11.0 },
      { 'name': '40-44', 'population': 10.0 },
      { 'name': '44-49', 'population': 11.0 },
      { 'name': '50.0 - np.int64(50)', 'tail': 1 }],
      'd': [{ 'name': 1, 'cat_pop': 38.0 },
      { 'name': 2, 'cat_pop': 21.0 },
      { 'name': 3, 'cat_pop': 21.0 },
      { 'name': 4, 'cat_pop': 20.0 }]
    }]

  }
}


export const DateNoDisplay: Story = {
  args: {
    data:
    [{'index': 0, 'date': '06/11/2021', 'date2': '06/11/2021'},
      {'index': 1, 'date': 'Nov, 22nd 2021', 'date2': '22/11/2021'},
      {'index': 2, 'date': '24th of November, 2021', 'date2': '24/11/2021'}],
    df_viewer_config: {
      column_config: [
      { col_name: 'index', displayer_args: {'displayer':'obj'} },
      { col_name: 'date', displayer_args: {'displayer':'obj'} },
      { col_name: 'date', displayer_args: {'displayer':'string'}},
      { col_name: 'date2', displayer_args: {'displayer':'obj'} },
      { col_name: 'date2', displayer_args: {'displayer':'string'}},
    ],
    pinned_rows:[],

  }
}
};

const MEDIUM= 300;

export const MedDFVHeight: Story = {
  args: {
    data:dictOfArraystoDFData({'a':NRandom(MEDIUM, 3,50), 'b':arange(MEDIUM)   }),
    df_viewer_config: {
      column_config: [
      {
        col_name: 'a',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8,
        },
        //tooltip_config: { tooltip_type: 'summary_series' },
      },
      {
        col_name: 'a',
        displayer_args: {
          displayer: 'integer',
          min_digits:2, max_digits:3
        },
      },
      {
        col_name: 'b',
        displayer_args: {
          displayer: 'obj',
        },
      },
    ],
    pinned_rows:[],
    component_config: {dfvHeight:200}
  },
  
    }
}