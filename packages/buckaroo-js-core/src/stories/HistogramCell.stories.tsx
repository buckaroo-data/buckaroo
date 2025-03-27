//import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
//import { fn } from "@storybook/test";
import { TypedHistogramCell } from "../components/DFViewerParts/HistogramCell";


    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/Renderers/Histogram",
  component:TypedHistogramCell,
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
} satisfies Meta<typeof TypedHistogramCell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {histogramArr:[
        {'cat_pop':33.0,
          'name': '2000-01-01 00:00:00'},
         {'cat_pop': 33.0,
          'name': '2001-01-01 00:00:00'},
         {'name': 'unique', 'unique': 67.0},
         {'NA': 33.0, 'name': 'NA'}
      ],
      'context': undefined
    }
};