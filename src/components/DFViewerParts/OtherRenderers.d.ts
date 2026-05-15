import { ValueFormatterFunc } from 'ag-grid-community';
export declare const getTextCellRenderer: (formatter: ValueFormatterFunc<any>) => (props: any) => import("react/jsx-runtime").JSX.Element;
export declare const getHighlightTextCellRenderer: (formatter: ValueFormatterFunc<any>, spec: {
    phrase?: string | string[];
    regex?: string;
}, color?: string) => (props: any) => import("react/jsx-runtime").JSX.Element;
export declare const LinkCellRenderer: (props: any) => import("react/jsx-runtime").JSX.Element;
export declare const Base64PNGDisplayer: (props: any) => import("react/jsx-runtime").JSX.Element;
export declare const SVGDisplayer: (props: any) => import("react/jsx-runtime").JSX.Element;
