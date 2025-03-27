//import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
//import { fn } from "@storybook/test";
import { TypedLineChartCell } from "../components/DFViewerParts/LineChartCell";


    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/Renderers/LineChart",
  component:TypedLineChartCell,
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
} satisfies Meta<typeof TypedLineChartCell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {histogramArr:[
        {'cat_pop':33.0,
          'name': '2000-01-01 00:00:00'},
         {'cat_pop': 33.0,
          'name': '2001-01-01 00:00:00'},
         {'cat_pop': 66, 'name':'unique'},
         {'cat_pop': 100, 'name':'end'},
      ]}
};

export const Composed: Story = {
  args: {histogramArr:[
        {'cat_pop':33.0,
          'name': '2000-01-01 00:00:00',
          'unique':100
        },
         {'cat_pop': 33.0,
          'unique': 20,
          'name': '2001-01-01 00:00:00'},
         {'cat_pop': 66, 
          'unique':40,
          'name':'unique'},
         {'cat_pop': 100, 
          'unique':100,
          'name':'end'},
      ]}
};