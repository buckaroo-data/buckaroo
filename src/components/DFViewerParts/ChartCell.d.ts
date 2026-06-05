import { default as React } from '../../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { ChartDisplayerA } from './DFWhole';
export interface HistogramNode {
    name: string;
    population: number;
}
export declare const formatter: (value: any, name: any, props: any) => any[];
export declare function FloatingTooltip({ items, x, y }: any): React.ReactPortal;
export interface LineObservation {
    'unique'?: number;
    'barRed'?: number;
    'barBlue'?: number;
    'barGray'?: number;
    'barCustom1'?: number;
    'barCustom2'?: number;
    'barCustom3'?: number;
    'lineRed'?: number;
    'lineBlue'?: number;
    'lineGray'?: number;
    'lineCustom1'?: number;
    'lineCustom2'?: number;
    'lineCustom3'?: number;
    'areaRed'?: number;
    'areaBlue'?: number;
    'areaGray'?: number;
    'areaCustom1'?: number;
    'areaCustom2'?: number;
    'areaCustom3'?: number;
    'areaUnique'?: number;
}
export declare const ChartColors: {
    unique: string;
    longtail: string;
    NA: string;
    cat_pop: string;
};
export declare function getChartColors(scheme: 'light' | 'dark'): {
    unique: string;
    longtail: string;
    NA: string;
    cat_pop: string;
};
export declare const getChartCell: (multiChartCellProps: ChartDisplayerA) => (props: any) => import("react/jsx-runtime").JSX.Element;
