import { StoryObj } from '@storybook/react';
import { BuckarooOptions, BuckarooState, DFMeta } from '../components/WidgetTypes';
declare const meta: {
    title: string;
    component: ({ dfMeta, buckarooState, buckarooOptions, }: {
        dfMeta: DFMeta;
        buckarooState: BuckarooState;
        buckarooOptions: BuckarooOptions;
    }) => import("react/jsx-runtime").JSX.Element;
    parameters: {
        layout: string;
    };
    tags: string[];
    argTypes: {};
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const Primary: Story;
export declare const NoCleaningNoPostProcessing: Story;
