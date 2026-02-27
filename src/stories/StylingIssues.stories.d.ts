import { StoryObj } from '@storybook/react';
declare const meta: {
    title: string;
    component: () => null;
    parameters: {
        layout: string;
    };
};
export default meta;
type Story = StoryObj<typeof meta>;
/** Baseline – 5 cols, 1-char headers, 1-2 digit values. Should look fine. (#599) */
export declare const FewCols_ShortHdr_ShortData: Story;
/** 5 cols, 1-char headers, 6-7 digit values. Data drives width, no contention. */
export declare const FewCols_ShortHdr_LongData: Story;
/** 5 cols, 12-18 char headers, 1-2 digit values. Header wider than data. */
export declare const FewCols_LongHdr_ShortData: Story;
/** 5 cols, long headers, long data. Both are wide; no contention at 5 cols. */
export declare const FewCols_LongHdr_LongData: Story;
/** 25 cols, 1-char headers, 1-2 digit values. Primary bug case (#595/#599). */
export declare const ManyCols_ShortHdr_ShortData: Story;
/** 25 cols, 1-char headers, 6-7 digit values. Data wants space (#596). */
export declare const ManyCols_ShortHdr_LongData: Story;
/** 25 cols, 12-18 char headers, 1-2 digit values. Headers want space (#596). */
export declare const ManyCols_LongHdr_ShortData: Story;
/** 25 cols, long headers, long data. Worst-case contention (#596). */
export declare const ManyCols_LongHdr_LongData: Story;
/** 15 cols with fitGridWidth. #595 repro — values show "..." without minWidth fix. */
export declare const ManyCols_LongHdr_YearData: Story;
/** 5 cols, values 3M–5.7B, float displayer. Shows why compact is needed (#597). */
export declare const LargeNumbers_Float: Story;
/** Same data as LargeNumbers_Float but using compact_number displayer (#597 fix). */
export declare const LargeNumbers_Compact: Story;
/** 5 cols, values tightly clustered 5.60B–5.68B, float displayer (#602 baseline). */
export declare const ClusteredBillions_Float: Story;
/** Same clustered data with compact_number – exposes precision loss (#602). */
export declare const ClusteredBillions_Compact: Story;
/** 10 long-header cols + pinned summary stats + left index. Tests #587 alignment. */
export declare const PinnedIndex_FewCols: Story;
/** 20 long-header cols + pinned summary stats. #587 alignment under width contention. */
export declare const PinnedIndex_ManyCols: Story;
/** 20 narrow cols + pinned rows. Cross-issue: #595 + #587 + #599. */
export declare const Mixed_ManyNarrow_WithPinned: Story;
/** 5 wide cols + pinned rows. #587 baseline (should look fine). */
export declare const Mixed_FewWide_WithPinned: Story;
