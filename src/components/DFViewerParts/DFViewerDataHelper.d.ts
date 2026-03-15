import { IDatasource } from 'ag-grid-community';
export type RawDataWrapper = {
    data: any[];
    length: number;
    data_type: 'Raw';
};
export type DatasourceWrapper = {
    datasource: IDatasource;
    data_type: 'DataSource';
    length: number;
};
export type DatasourceOrRaw = RawDataWrapper | DatasourceWrapper;
export type DFData = any[];
export declare const createRawDataWrapper: (data: any[]) => RawDataWrapper;
export declare const createDatasourceWrapper: (data: DFData, delay_in_milliseconds?: number) => DatasourceWrapper;
export declare const dictOfArraystoDFData: (dict: Record<string, any[]>) => DFData;
export declare const arange: (N: number) => number[];
export declare const NRandom: (N: number, low: number, high: number) => number[];
export declare const rd: RawDataWrapper;
export declare const HistogramSummaryStats: DFData;
