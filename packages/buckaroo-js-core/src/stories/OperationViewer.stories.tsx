import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { OperationViewer } from "../components/Operations";
import { sampleOperations, dataCleaningOps, bakedCommandConfig, manyOperations } from "../components/OperationExamples";
import "../style/dcf-npm.css"
import { Operation } from "../components/OperationUtils";
import { CommandConfigT } from "../components/CommandUtils";

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
  title: "Buckaroo/Chrome/OperationViewer-in-stories-dir",
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

export const Default: Story = {
  args: {
      operations: sampleOperations,
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config: bakedCommandConfig
  },
};

export const Empty: Story = {
  args: {
      operations:[],
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config:bakedCommandConfig
  },
};

export const SingleOperation: Story = {
  args: {
      operations: [sampleOperations[0]],
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config: bakedCommandConfig
  },
};

export const DataCleaning: Story = {
  args: {
      operations: dataCleaningOps,
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config: bakedCommandConfig
  },
};

export const ManyOperations: Story = {
  args: {
      operations: manyOperations,
      activeColumn: 'foo-column',
      allColumns: ['foo-col', 'bar-col', 'baz-col'],
      command_config: bakedCommandConfig
  },
};
