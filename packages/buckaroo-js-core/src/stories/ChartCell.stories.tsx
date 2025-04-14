//import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
//import { fn } from "@storybook/test";
import { getChartCell } from "../components/DFViewerParts/ChartCell";
import { ChartDisplayerA } from "../components/DFViewerParts/DFWhole";


const getChartCellWrapper = ({value, dispArgs}: {value:any, dispArgs:ChartDisplayerA}) => {
  const ChartCell = getChartCell(dispArgs)
  return ChartCell({value});
}

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/Renderers/ChartCell",
  component:getChartCellWrapper,
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
} satisfies Meta<typeof getChartCellWrapper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {value: [
        {lineRed:33.0,  name: '2000-01-01 00:00:00'},
        {lineRed: 33.0, name: '2001-01-01 00:00:00'},
        {lineRed: 66, name:'unique'},
        {lineRed: 100, name:'end'},
      ],
      dispArgs: {displayer:"chart"}
    }
};

export const Area: Story = {
  args: {value:[
        {areaUnique:100, name: '2000-01-01 00:00:00'},
        {areaUnique: 20, name: '2001-01-01 00:00:00'},
        {areaUnique:40,  name:'unique'},
        {areaUnique:100, name:'end'},
      ],
      dispArgs: {displayer:"chart"}
    }
};
export const Composed: Story = {
  args: {value:[
        {lineRed:33.0, areaGray:100, barCustom3:40, barCustom1:40,
          name: '2000-01-01 00:00:00'},
         {lineRed: 33.0, areaGray: 20,
          name: '2001-01-01 00:00:00'},
         {lineRed: 66,  areaGray:40, barCustom2:60,
          name:'unique'},
         {lineRed: 100, areaGray:100, barCustom1:40,
          name:'end'},
      ],
       dispArgs: {displayer:"chart"}
    }
};

export const ComposedCustomColor: Story = {
  args: {value:[
        {lineRed:33.0, areaGray:100, barCustom3:40, barCustom1:40,
          name: '2000-01-01 00:00:00'},
         {lineRed: 33.0, areaGray: 20,
          name: '2001-01-01 00:00:00'},
         {lineRed: 66,  areaGray:40, barCustom2:60,
          name:'unique'},
         {lineRed: 100, areaGray:100, barCustom1:40,
          name:'end'},
      ],
       dispArgs: {displayer:"chart",
         colors:{custom1_color:"pink", custom2_color:"brown", custom3_color:"beige"}}
    }
};