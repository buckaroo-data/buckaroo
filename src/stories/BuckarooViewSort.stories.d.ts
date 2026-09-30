import { StoryObj } from '@storybook/react';
import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { HeaderSort } from '../components/DFViewerParts/gridUtils';
declare const meta: {
    title: string;
    component: React.FC<{
        sort?: HeaderSort;
    }>;
    parameters: {
        layout: string;
    };
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const HostSort: Story;
