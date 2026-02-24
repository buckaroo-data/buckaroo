import { DFWhole, TooltipConfig } from './DFWhole';
import { ITooltipParams } from '@ag-grid-community/core';
export declare function getBakedDFViewer(seriesDf: DFWhole): (_props: ITooltipParams) => import("react/jsx-runtime").JSX.Element;
export declare const getSimpleTooltip: (tooltipField: string) => (props: ITooltipParams) => import("react/jsx-runtime").JSX.Element | undefined;
interface RealTooltipParams {
    tooltipField: string;
    tooltipComponent: (props: ITooltipParams) => React.Component;
}
interface EmptyTooltipParams {
}
export type CDTooltipParams = RealTooltipParams | EmptyTooltipParams;
export declare const getTooltipParams: (tooltip_config?: TooltipConfig) => CDTooltipParams;
export {};
