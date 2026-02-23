import { StoryObj } from '@storybook/react';
declare const meta: {
    title: string;
    parameters: {
        layout: string;
    };
    tags: string[];
};
export default meta;
/** Fraction mode (Jupyter/Marimo) — 300 rows, grid takes ~half of 600px container */
export declare const FractionMode: StoryObj;
/** Fraction mode with short table — 3 rows should auto-size, not take half screen */
export declare const FractionModeShort: StoryObj;
/** Fixed mode (Colab/VSCode) — 300 rows, grid is exactly 400px */
export declare const FixedMode: StoryObj;
/** Fixed mode with short table — still 400px (fixed mode ignores short) */
export declare const FixedModeShort: StoryObj;
/** Fill mode (MCP standalone) — 300 rows, grid fills the full 600px container */
export declare const FillMode: StoryObj;
/** Fill mode with short table — 3 rows should auto-size, NOT stretch to 600px */
export declare const FillModeShort: StoryObj;
/** No heightMode set — backward compat, should behave like fraction */
export declare const NoHeightMode: StoryObj;
/** No heightMode, short table — backward compat short mode */
export declare const NoHeightModeShort: StoryObj;
