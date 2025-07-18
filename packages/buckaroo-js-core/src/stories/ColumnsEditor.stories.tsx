import  { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { ColumnsEditor } from "../components/ColumnsEditor";
import { Operation } from "../components/OperationUtils";
import { OperationResult } from "../components/DependentTabs";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import "../style/dcf-npm.css"
import { sampleOperations, bakedCommandConfig, dataCleaningOps, manyOperations } from "../components/OperationExamples";


const INDEX_COL_CONFIG : NormalColumnConfig  = {
          col_name: 'index',
	  header_name: 'index',
          displayer_args: {
            displayer: 'string',
          },
        }

const left_col_configs = [INDEX_COL_CONFIG];


const df_viewer_config: DFViewerConfig = {
  column_config: [
    {
      col_name: "index",
      header_name: "index",
      displayer_args: { displayer: "integer", min_digits: 3, max_digits: 5 },
    },
    {
      col_name: "svg_column",
      header_name: "svg_column",
      displayer_args: { displayer: "SVGDisplayer" },
    },
    {
      col_name: "link_column",
      header_name: "link_column",
      displayer_args: { displayer: "linkify" },
    },
    {
      col_name: "nanObject",
      header_name: "nanObject",
      displayer_args: { displayer: "integer", min_digits: 3, max_digits: 5 },
      color_map_config: {
        color_rule: "color_map",
        map_name: "BLUE_TO_YELLOW",
        val_column: "tripduration",
      },
    },
  ],
  extra_grid_config: { rowHeight: 105 },
  component_config: { height_fraction: 1 },
  pinned_rows: [],
  left_col_configs
};

const baseOperationResults: OperationResult = {
  transformed_df: {
    dfviewer_config: {
      pinned_rows: [],
      column_config: [],
      left_col_configs
    },
    data: [],
  },
  generated_py_code: "default py code",
  transform_error: undefined,
};

const meta = {
  title: "Buckaroo/ColumnsEditor",
  component: ColumnsEditor,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ColumnsEditor>;

export default meta;
type Story = StoryObj<typeof meta> | any;

export const Default: Story = {
  render: () => {
    const [operations, setOperations] = useState<Operation[]>(sampleOperations);
    return (
      <ColumnsEditor
        df_viewer_config={df_viewer_config}
        activeColumn="index"
        operation_result={baseOperationResults}
        command_config={bakedCommandConfig}
        operations={operations}
        setOperations={setOperations}
      />
    );
  },
};

export const Empty: Story = {
  render: () => {
    const [operations, setOperations] = useState<Operation[]>([]);
    return (
      <ColumnsEditor
        df_viewer_config={df_viewer_config}
        activeColumn="index"
        operation_result={baseOperationResults}
        command_config={bakedCommandConfig}
        operations={operations}
        setOperations={setOperations}
      />
    );
  },
};

export const SingleOperation: Story = {
  render: () => {
    const [operations, setOperations] = useState<Operation[]>([sampleOperations[0]]);
    return (
      <ColumnsEditor
        df_viewer_config={df_viewer_config}
        activeColumn="index"
        operation_result={baseOperationResults}
        command_config={bakedCommandConfig}
        operations={operations}
        setOperations={setOperations}
      />
    );
  },
};

export const DataCleaning: Story = {
  render: () => {
    const [operations, setOperations] = useState<Operation[]>(dataCleaningOps);
    return (
      <ColumnsEditor
        df_viewer_config={df_viewer_config}
        activeColumn="index"
        operation_result={baseOperationResults}
        command_config={bakedCommandConfig}
        operations={operations}
        setOperations={setOperations}
      />
    );
  },
};

export const ManyOperations: Story = {
  render: () => {
    const [operations, setOperations] = useState<Operation[]>(manyOperations);
    return (
      <ColumnsEditor
        df_viewer_config={df_viewer_config}
        activeColumn="index"
        operation_result={baseOperationResults}
        command_config={bakedCommandConfig}
        operations={operations}
        setOperations={setOperations}
      />
    );
  },
}; 
