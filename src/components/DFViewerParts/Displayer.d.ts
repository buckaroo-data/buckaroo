import { ValueFormatterFunc, ValueFormatterParams } from 'ag-grid-community';
import { DisplayerArgs, FloatDisplayerA, DatetimeLocaleDisplayerA, StringDisplayerA, ObjDisplayerA, CellRendererArgs, FormatterArgs } from './DFWhole';
export declare const basicIntFormatter: Intl.NumberFormat;
export declare const getStringFormatter: (args: StringDisplayerA) => (params: ValueFormatterParams) => string;
export declare const isValidDate: (possibleDate: any) => boolean;
export declare const dateDisplayerDefault: (d: Date) => string;
export declare const getObjectFormatter: (fArgs: ObjDisplayerA) => (params: ValueFormatterParams) => string;
export declare const objFormatter: (params: ValueFormatterParams) => string;
export declare const boolDisplayer: (val: boolean) => "" | "True" | "False";
export declare const booleanFormatter: (params: ValueFormatterParams) => string;
export declare const getFloatFormatter: (hint: FloatDisplayerA) => (params: ValueFormatterParams) => string;
export declare const getDatetimeFormatter: (colHint: DatetimeLocaleDisplayerA) => (params: ValueFormatterParams) => string;
export declare const getCompactNumberFormatter: () => (params: ValueFormatterParams) => string;
/**
 * Format a duration string into a human-readable representation like "1d 2h 3m 4.5s".
 * Accepts:
 *   - ISO 8601: "P1DT2H3M4.5S"
 *   - Pandas timedelta: "1 days 02:03:04", "0 days 00:30:00.500000"
 */
export declare const formatDuration: (raw: string) => string;
/** @deprecated Use formatDuration instead */
export declare const formatIsoDuration: (raw: string) => string;
export declare const getDurationFormatter: () => (params: ValueFormatterParams) => string;
export declare const defaultDatetimeFormatter: (params: ValueFormatterParams) => string;
export declare function getFormatter(fArgs: FormatterArgs): ValueFormatterFunc<unknown>;
export declare function getCellRenderer(crArgs: CellRendererArgs): "agCheckboxCellRenderer" | ((props: {
    api: import('ag-grid-community').GridApi;
    colDef: import('ag-grid-community').ColDef;
    column: import('ag-grid-community').Column;
    context: import('ag-grid-community').Context;
    value: any;
}) => import("react/jsx-runtime").JSX.Element);
export declare function getFormatterFromArgs(dispArgs: DisplayerArgs): ValueFormatterFunc<unknown, any> | undefined;
