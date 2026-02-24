import { CellClassParams } from 'ag-grid-community';
import { ColorMappingConfig, ColorMapRules, ColorCategoricalRules, ColorWhenNotNullRules, ColorFromColumn } from './DFWhole';
export declare function getHistoIndex(val: number, histogram_edges: number[]): number;
export declare function colorMap(cmr: ColorMapRules): {
    cellStyle: (params: CellClassParams) => {
        backgroundColor: string;
    };
};
export declare function categoricalColor(cmr: ColorCategoricalRules): {
    cellStyle: (params: CellClassParams) => {
        backgroundColor: string;
    };
};
export declare function colorNotNull(cmr: ColorWhenNotNullRules): {
    cellStyle: (params: CellClassParams) => {
        backgroundColor: string;
    };
};
export declare function colorFromColumn(cmr: ColorFromColumn): {
    cellStyle: (params: CellClassParams) => {
        backgroundColor: any;
    };
};
export declare function getStyler(cmr: ColorMappingConfig): {
    cellStyle: (params: CellClassParams) => {
        backgroundColor: any;
    };
};
