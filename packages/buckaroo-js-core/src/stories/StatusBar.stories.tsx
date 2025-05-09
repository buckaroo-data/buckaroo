import type { Meta, StoryObj } from "@storybook/react";

import "../style/dcf-npm.css"
import _ from "lodash";
import { StatusBar } from "../components/StatusBar";
import { BuckarooOptions, BuckarooState, DFMeta } from "../components/WidgetTypes";
import { useState } from "react";

const StatusBarWrap = ({
    dfMeta,
    buckarooState,
    buckarooOptions,
}: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    buckarooOptions: BuckarooOptions;
}) => {
  const [bState, setBuckarooState] = useState<BuckarooState>(buckarooState);

  return (
      <div className="dcf-root flex flex-col" 
      style={{ width: "800px", height: "300px", border:"1px solid red" }}>
            <div
                className="orig-df"
                style={{
                    // height: '450px',
                    overflow: "hidden",
                }}
            >

      <StatusBar
      dfMeta={dfMeta}
      buckarooState={bState}
      setBuckarooState={setBuckarooState}
      buckarooOptions={buckarooOptions}
      heightOverride={150}
      />
      </div>
      <pre> {JSON.stringify(bState, undefined, 4)}</pre>
     </div>);
}

    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/StatusBar",
  component:StatusBarWrap,
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
} satisfies Meta<typeof StatusBarWrap>;

export default meta;
type Story = StoryObj<typeof meta>;

const dfm:DFMeta = {
  total_rows:378,
  columns:7,
  filtered_rows:297,
  rows_shown:297
}

const bo:BuckarooOptions =  {
  sampled: ["sample_strat1", "sample_strat2", ""],
  cleaning_method: ["clean_strat1", "clean_strat2", ""],
  post_processing: ["", "post1", "post2"],
  df_display: ["main", "summary"],
  show_commands: ["on", "off"]
}

const bs:BuckarooState = {
  sampled:false,
  cleaning_method:false,
  quick_command_args:{},
  post_processing:false,
  df_display:"main",
  show_commands:false

}

export const Primary: Story = {
  args: {
    dfMeta:dfm,
    buckarooState:bs,
    buckarooOptions:bo,
  }
}


export const NoCleaningNoPostProcessing: Story = {
  args: {
    dfMeta:dfm,
    buckarooState:bs,
    buckarooOptions:{
      sampled: ["sample_strat1", "sample_strat2", ""],
      cleaning_method: [],
      post_processing: [],
      df_display: ["main", "summary"],
      show_commands: ["on", "off"]
    }
  }
}
