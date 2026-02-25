import { StoryObj } from '@storybook/react';
import { default as React } from '../../node_modules/.pnpm/react@18.3.1/node_modules/react';
declare const meta: {
    title: string;
    component: React.FC<{
        delayed?: boolean;
    }>;
    parameters: {
        layout: string;
    };
    tags: string[];
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const Primary: Story;
export declare const WithDelay: Story;
