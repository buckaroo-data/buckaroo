import { StoryObj } from '@storybook/react';
import { DFViewerConfig } from '../components/DFViewerParts/DFWhole';
import { DatasourceOrRaw } from '../components/DFViewerParts/DFViewerDataHelper';
declare const meta: {
    title: string;
    component: ({ data_wrapper, df_viewer_config, }: {
        data_wrapper: DatasourceOrRaw;
        df_viewer_config: DFViewerConfig;
    }) => import("react/jsx-runtime").JSX.Element;
    parameters: {
        layout: string;
    };
    tags: string[];
    argTypes: {};
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const DefaultNoTheme: Story;
export declare const CustomAccent: Story;
export declare const ForcedDark: Story;
export declare const ForcedLight: Story;
export declare const FullCustom: Story;
