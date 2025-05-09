import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { OperationsList2 } from "../components/OperationsList";
import { getOperationKey, Operation } from "../components/OperationUtils";
import { sampleOperations, dataCleaningOps, manyOperations } from "../components/OperationExamples";


const OperationsListWrapper = ({ operations }: { operations: Operation[] }) => {
    const [ops, setOps] = React.useState<Operation[]>(operations);

    const [activeKey, setActiveKey] = React.useState<string>(getOperationKey(ops, 1));

    return <OperationsList2 operations={ops} setOperations={setOps}
                            activeKey={activeKey} setActiveKey={setActiveKey}
     />;
};

const meta = {
    title: "Components/OperationsList",
    component: OperationsListWrapper,
    parameters: {
        layout: "centered",
    },
    tags: ["autodocs"],
} satisfies Meta<typeof OperationsListWrapper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
    args: {
        operations: sampleOperations,
    },
};

export const Empty: Story = {
    args: {
        operations: [],
    },
};

export const SingleOperation: Story = {
    args: {
        operations: [sampleOperations[0]],
    },
};

export const DataCleaning: Story = {
    args: {
        operations: dataCleaningOps,
    },
};

export const ManyOperations: Story = {
    args: {
        operations: manyOperations,
    },
}; 