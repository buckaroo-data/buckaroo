import type { Meta, StoryObj } from "@storybook/react";
import { DFData, DFViewerConfig } from "../components/DFViewerParts/DFWhole";
import { SetColumFunc } from "../components/DFViewerParts/gridUtils";

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
    setActiveCol?: SetColumFunc;
    // these are the parameters that could affect the table,
    // dfviewer doesn't need to understand them, but it does need to use
    // them as keys to get updated data
    outside_df_params?: any;
    error_info?: string;
}) => {

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
export const DateNoDisplay: Story = {
  args: {
    df_data:    [{'index': 0, 'date': '06/11/2021', 'date2': '06/11/2021'},
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