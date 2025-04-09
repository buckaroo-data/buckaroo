import type { Meta, StoryObj } from "@storybook/react";
import { ShadowDomWrapper } from "./StoryUtils";


const CSSPlay = ({a}: {
    a:number}) => {
	console.log("a", a)
  return (<ShadowDomWrapper>
      <div style={{height:500, width:800}} className={"ag-theme-alpine-dark"}>
	  <span className={"ag-sort-indicator-container"} style={{color:"green", height:50, width:50, border:"3px solid orange" }}  data-ref="eSortIndicator">
          <span data-ref="eSortOrder" className={"ag-sort-indicator-icon ag-sort-order ag-hidden"} aria-hidden="true">1</span>
          <span data-ref="eSortAsc" className={"ag-sort-indicator-icon ag-sort-ascending-icon"} aria-hidden="true">
          <span className={"ag-icon ag-icon-asc"} style={{color:"black"}} unselectable="on" role="presentation">
	   </span></span>

	  </span>
	  <span className={"ag-icon ag-icon-asc"} unselectable="on" role="presentation">
	  </span>
     </div>
     </ShadowDomWrapper>);
}


// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "CSSPlay",
    component:CSSPlay,
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
} satisfies Meta<typeof CSSPlay>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
    args: { a: 5}}
