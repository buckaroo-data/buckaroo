import { Meta, StoryObj } from '@storybook/react';
import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
declare const Single: React.FC<{
    rowCount: number;
    autoHeight: boolean;
    hostHeight: number;
}>;
declare const Stacked: React.FC<{
    rowCounts: [number, number];
    autoHeight: boolean;
    hostHeight: number;
}>;
declare const meta: Meta<typeof Single>;
export default meta;
type SingleStory = StoryObj<typeof Single>;
export declare const SmallDfFixed: SingleStory;
export declare const SmallDfAutoHeight: SingleStory;
export declare const LargeDfFixed: SingleStory;
export declare const LargeDfAutoHeight: SingleStory;
export declare const SmallDfShortHostFixed: SingleStory;
export declare const SmallDfShortHostAutoHeight: SingleStory;
export declare const LargeDfShortHostFixed: SingleStory;
export declare const LargeDfShortHostAutoHeight: SingleStory;
export declare const StackedAutoHeightSmallLarge: StoryObj<typeof Stacked>;
export declare const StackedFixedSmallLarge: StoryObj<typeof Stacked>;
