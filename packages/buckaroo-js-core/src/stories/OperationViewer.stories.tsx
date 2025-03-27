import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { OperationViewer } from "../components/Operations";
import { Operation, OperationDefaultArgs, sym } from "../components/OperationUtils";
import { CommandArgSpec, CommandConfigT, symDf } from "../components/CommandUtils";


const OperationViewerWrap = ({
    operations,
    activeColumn,
    allColumns,
    command_config,
}: {
    operations: Operation[];
    activeColumn: string;
    allColumns: string[];
    command_config: CommandConfigT;
}) => {
    const [usedOperations, setOperations] = React.useState<Operation[]>(operations);
    return (<OperationViewer
	    operations={usedOperations}
	    setOperations={setOperations}
	    activeColumn={activeColumn}
	    allColumns={allColumns}
	    command_config={command_config} />)
}
	    
    

// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/Chrome/OperationViewer",
  component:OperationViewerWrap,
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
} satisfies Meta<typeof OperationViewerWrap>;

export default meta;
type Story = StoryObj<typeof meta>;


const bakedOperationDefaults: OperationDefaultArgs = {
    dropcol: [sym('dropcol'), symDf, 'col'],
    fillna: [sym('fillna'), symDf, 'col', 8],
    remove_outliers: [sym('remove_outliers'), symDf, 'col', 0.02],
    search: [sym('search'), symDf, 'col', 'term'],
    resample: [sym('resample'), symDf, 'col', 'monthly', {}],
  };

const bakedArgSpecs: CommandArgSpec = {
      dropcol: [null],
    fillna: [[3, 'fillVal', 'type', 'integer']],
    remove_outliers: [[3, 'tail', 'type', 'float']],
    search: [[3, 'needle', 'type', 'string']],
    resample: [
      [3, 'frequency', 'enum', ['daily', 'weekly', 'monthly']],
      [4, 'colMap', 'colEnum', ['null', 'sum', 'mean', 'count']],
    ],
  };
 const bakedCommandConfig: CommandConfigT = {
    argspecs: bakedArgSpecs,
    defaultArgs: bakedOperationDefaults,
  };

const bakedOperations: Operation[] = [
    [sym('dropcol'), symDf, 'col1'],
    [sym('fillna'), symDf, 'col2', 5],
    [sym('resample'), symDf, 'month', 'monthly', {}],
  ];
// More on writing stories with args:
// https://storybook.js.org/docs/writing-stories/args
export const Primary: Story = {
  args: {
      operations:bakedOperations,
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config:bakedCommandConfig
  },
};

export const NoOps: Story = {
  args: {
      operations:[],
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config:bakedCommandConfig
  },
};
