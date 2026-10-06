import { StoryObj } from '@storybook/react';
import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
interface StatsUpdateChannelProps {
    rowDelayMs: number;
    stateDelayMs: number;
}
declare const meta: {
    title: string;
    component: React.FC<StatsUpdateChannelProps>;
    parameters: {
        layout: string;
    };
    argTypes: {
        rowDelayMs: {
            control: {
                type: "range";
                min: number;
                max: number;
                step: number;
            };
        };
        stateDelayMs: {
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
export declare const Manual: Story;
