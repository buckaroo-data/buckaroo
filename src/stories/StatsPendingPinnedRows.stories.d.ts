import { StoryObj } from '@storybook/react';
import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
interface DelayedStatsProps {
    statsDelayMs: number;
    autoDeliver: boolean;
}
declare const meta: {
    title: string;
    component: React.FC<DelayedStatsProps>;
    parameters: {
        layout: string;
    };
    argTypes: {
        statsDelayMs: {
            control: {
                type: "range";
                min: number;
                max: number;
                step: number;
            };
        };
    };
};
export default meta;
type Story = StoryObj<typeof meta>;
export declare const Delayed: Story;
export declare const Manual: Story;
