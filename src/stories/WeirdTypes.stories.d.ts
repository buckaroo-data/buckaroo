import { StoryObj } from '@storybook/react';
import { DFData, DFViewerConfig } from '../components/DFViewerParts/DFWhole';
declare const meta: {
    title: string;
    component: ({ df_data, df_viewer_config, }: {
        df_data: DFData;
        df_viewer_config: DFViewerConfig;
    }) => import("react/jsx-runtime").JSX.Element;
    parameters: {
        layout: string;
    };
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const PandasWeirdTypes: Story;
export declare const PolarsWeirdTypes: Story;
