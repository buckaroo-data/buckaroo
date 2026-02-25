import { StoryObj } from '@storybook/react';
import { default as React } from '../../node_modules/.pnpm/react@18.3.1/node_modules/react';
type OutsideKey = "A" | "B";
type DelayByKey = Partial<Record<OutsideKey, number>>;
type DataVariant = "default" | "sortable";
declare const meta: {
    title: string;
    component: React.FC<{
        delayed?: boolean;
        delayByKey?: DelayByKey;
        dataVariant?: DataVariant;
        enableSort?: boolean;
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
export declare const AsymmetricDelayASlowBFast: Story;
export declare const AsymmetricDelayBSlowAFast: Story;
export declare const SortAndToggle: Story;
