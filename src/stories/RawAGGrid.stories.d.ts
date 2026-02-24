import { StoryObj } from '@storybook/react';
import { DFData } from '../components/DFViewerParts/DFWhole';
import { ColDef } from 'ag-grid-community';
declare const meta: {
    title: string;
    component: ({ colDefs, data }: {
        colDefs: Record<string, ColDef[]>;
        data: Record<string, DFData>;
    }) => import("react/jsx-runtime").JSX.Element;
    parameters: {
        layout: string;
    };
    tags: string[];
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const Default: Story;
