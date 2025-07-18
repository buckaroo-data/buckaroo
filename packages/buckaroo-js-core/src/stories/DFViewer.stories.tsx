import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { DFData, DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { SetColumnFunc } from "../components/DFViewerParts/gridUtils";

import "../style/dcf-npm.css"
import { DFViewer } from "../components/DFViewerParts/DFViewerInfinite";

const DFViewerWrap = ({
    df_data,
    df_viewer_config,
    summary_stats_data,
    activeCol,
    setActiveCol,
}: {
    df_data:DFData,
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: DFData;
    activeCol?: string;
    setActiveCol?: SetColumnFunc;
    // these are the parameters that could affect the table,
    // dfviewer doesn't need to understand them, but it does need to use
    // them as keys to get updated data
    outside_df_params?: any;
    error_info?: string;
}) => {

  if(setActiveCol === undefined) {
    //@ts-ignore
    let [activeCol, setActiveCol] = useState('b');
  }
  return (
     <div style={{height:500, width:800}}>
      <DFViewer
      df_data={df_data}
      df_viewer_config={df_viewer_config}
      summary_stats_data={summary_stats_data}
      activeCol={activeCol}
      setActiveCol={setActiveCol}
    />
     </div>);
}

    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/DFViewer",
  component:DFViewerWrap,
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
} satisfies Meta<typeof DFViewerWrap>;

export default meta;
type Story = StoryObj<typeof meta>;

const INDEX_COL_CONFIG:NormalColumnConfig =         {
          col_name: 'index',
	  header_name: 'index',
          displayer_args: {
            displayer: 'string',
          },
        }

const left_col_configs = [INDEX_COL_CONFIG];

export const Primary: Story = {
  args: {
    df_data: [
      {'a':20, 'b':"foo"},
      {'a':30, 'b':"bar"}
    ],
    df_viewer_config: {
      column_config: [
      {
        col_name: 'a',
	header_name: 'a1',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8,
        },
        //tooltip_config: { tooltip_type: 'summary_series' },
      },
      {
        col_name: 'a',
	header_name: 'a2',
        displayer_args: {
          displayer: 'integer',
          min_digits:2, max_digits:3
        },
      },
      {
        col_name: 'b',
	header_name: 'b',
        displayer_args: {
          displayer: 'obj',
        },
      },
    ],
      pinned_rows:[],
      left_col_configs
  },
  
    }
}
export const Tooltip: Story = {
  args: {
    df_data:    [
      {index: 0, date: '06/11/2021',             date2: '06/11/2021', tt:'foo'},
      {index: 1, date: 'Nov, 22nd 2021',         date2: '22/11/2021', tt:'bar'},
      {index: 2, date: '24th of November, 2021', date2: '24/11/2021', tt:'baz'},
      {index: 3, date: '24th of November, 2021', date2: '24/11/2021'},
      {index: 4, date: '24th of November, 2021', date2: '24/11/2021', tt:9999},
      {index: 5, date: '24th of November, 2021', date2: '24/11/2021', tt:'baz'}],

    df_viewer_config: {
      column_config: [
	{ col_name: 'index', header_name: 'index', displayer_args: {'displayer':'obj'} },
	{ col_name: 'date', header_name:  'date',  displayer_args: {'displayer':'string'},
        tooltip_config: { 'tooltip_type':'simple', 'val_column': 'tt'}
    
    },
	{ col_name: 'date2', header_name: 'date2', displayer_args: {'displayer':'string'}},
    ],
    pinned_rows:[],
      left_col_configs
  }
}
};

export const ColorFromCol: Story = {
  args: {
    df_data:    [
      {index: 0, date: '06/11/2021',             color:"red"},
      {index: 1, date: 'Nov, 22nd 2021',         color:"#f8f8a1"},
      {index: 2, date: '24th of November, 2021', color:"teal"},
      {index: 3, date: '24th of November, 2021', color:"#aaa"},
      {index: 4, date: '24th of November, 2021'},
      {index: 5, date: '24th of November, 2021'}],
    df_viewer_config: {
      column_config: [
	{ col_name: 'index', header_name: 'index', displayer_args: {'displayer':'obj'} },
        {col_name: 'date', header_name: 'date',  displayer_args: {'displayer':'string'},
          color_map_config: {
            color_rule: "color_from_column",
            val_column: "color"}}],

      pinned_rows:[],
      left_col_configs
   }
  }
}

const lineChart = [
  {lineRed:33.0,  name: '2000-01-01 00:00:00'},
  {lineRed: 33.0, name: '2001-01-01 00:00:00'},
  {lineRed: 66, name:'unique'},
  {lineRed: 100, name:'end'},
]
export const Chart: Story = {
  args: {
    df_data:    [
      {index: 0, chart1: lineChart}],
    df_viewer_config: {
      column_config: [
        {col_name: 'index', header_name: 'index', displayer_args: {'displayer':'obj'} },
        {col_name: 'chart1', header_name: 'chart1', displayer_args: {'displayer':'chart'}}],        
      pinned_rows:[],
      left_col_configs
   }
  }
}
