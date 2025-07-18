import type { Meta, StoryObj } from "@storybook/react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { SetColumnFunc } from "../components/DFViewerParts/gridUtils";
import { DatasourceOrRaw, 
  rd } from "../components/DFViewerParts/DFViewerDataHelper";

const DFViewerInfiniteWrap = ({
    data_wrapper,
    df_viewer_config,
    summary_stats_data,
    activeCol,
    setActiveCol,
    outside_df_params,
    error_info,
}: {
    data_wrapper: DatasourceOrRaw;
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: any[];
    activeCol?: string;
    setActiveCol?: SetColumnFunc;
    outside_df_params?: any;
    error_info?: string;
}) => {
  const defaultSetColumnFunc = (newCol:string):void => {
    console.log("defaultSetColumnFunc", newCol)
  }
  const sac:SetColumnFunc = setActiveCol || defaultSetColumnFunc;


  return (
     <div style={{height:500, width:800}}>
      <DFViewerInfinite
        data_wrapper={data_wrapper}
        df_viewer_config={df_viewer_config}
        summary_stats_data={summary_stats_data}
        activeCol={activeCol}
        setActiveCol={sac}
        outside_df_params={outside_df_params}
        error_info={error_info} />
     </div>);
}

    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/DFViewerInfiniteRaw",
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


const INDEX_COL_CONFIG : NormalColumnConfig = {
          col_name: 'index',
	  header_name: 'index',
          displayer_args: {
            displayer: 'string',
          },
        }

const left_col_configs = [INDEX_COL_CONFIG];


export const Primary: Story = {
  args: {
    data_wrapper:rd,
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
