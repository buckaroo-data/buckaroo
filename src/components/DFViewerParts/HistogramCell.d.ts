import { ColDef, Column, Context, GridApi } from 'ag-grid-community';
export interface HistogramNode {
    name: string;
    population: number;
}
export declare const formatter: (value: any, name: any, props: any) => any[];
export interface HistogramBar {
    'cat_pop'?: number;
    'name': string;
    'NA'?: number;
    'longtail'?: number;
    'unique'?: number;
    'population'?: number;
}
export declare const HistogramCell: (props: {
    api: GridApi;
    colDef: ColDef;
    column: Column;
    context: Context;
    value: any;
}) => import("react/jsx-runtime").JSX.Element;
export declare const TypedHistogramCell: ({ histogramArr, context, className, colorScheme }: {
    histogramArr: HistogramBar[];
    context: any;
    className?: string;
    colorScheme?: "light" | "dark";
}) => import("react/jsx-runtime").JSX.Element;
