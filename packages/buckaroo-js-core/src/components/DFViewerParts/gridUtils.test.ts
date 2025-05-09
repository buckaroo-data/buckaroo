//import { add, multiply } from "../src/math";

import { 
    extractSDFT,  
    extractPinnedRows,
    dfToAgrid,
    getHeightStyle2,
    getAutoSize,

} from './gridUtils';
import * as _ from "lodash";
import { DFData, DFViewerConfig, PinnedRowConfig } from "./DFWhole";
import { getFloatFormatter } from './Displayer';
import { ValueFormatterParams } from '@ag-grid-community/core';

describe("testing utility functions in gridUtils ", () => {
  // mostly sanity checks to help develop gridUtils

  it("should test getFormater", () => {
    //  expect(getFormatter({displayer: 'string'})).toBe(stringFormatter)
    // expect(getFormatter({displayer: 'obj'})).toBe(objFormatter);
  });

  it("should format floats with a consistently spaced decimal pont", () => {
    const floatFormatter = getFloatFormatter(
      {'displayer':'float', 'min_fraction_digits':0, 'max_fraction_digits':3})
    const res1 = floatFormatter({'value': 1.997} as ValueFormatterParams);
    expect(res1).toBe("1.997");
    const res2 = floatFormatter({'value': 1.000} as ValueFormatterParams);
    expect(res2).toBe("1    ");
    const res3 = floatFormatter({'value': 1} as ValueFormatterParams);
    expect(res3).toBe("1    ");
    const res4 = floatFormatter({'value': 31} as ValueFormatterParams);
    expect(res4).toBe("31    ");

    const res5 = floatFormatter({'value': 1.5} as ValueFormatterParams);
    expect(res5).toBe("1.5  ");
  });

  it("should extract sdfts when only that is present from summary stats looking DFData ", () => {
    const basicSDF:DFData = [
      {'index': 'histogram_bins',     'a':[2,3]},
      {'index': 'histogram_log_bins', 'a':[20,30], 'b': [10, 20]}
    ];
    const expected = {
      'a': {'histogram_bins': [2,3], 'histogram_log_bins': [20, 30]},
      'b': {'histogram_bins': [],    'histogram_log_bins': [10, 20]}
    };
    const result = extractSDFT(basicSDF);
    expect(result).toEqual(expected);
  });

  describe("extractSDFT", () => {
    it("should extract SDFT data correctly", () => {
      const data: DFData = [
        { index: "row1", value: 1 },
        { index: "row2", value: 2 }
      ];
      const result = extractSDFT(data);
	expect(result).toEqual({});
    });
    it("should extract SDFT when present ", () => {
      const data: DFData = [
        { index: "row1", a:20 },
	{ index: 'histogram_bins', a:[2,3]},
        { index: "row2", a:30, b:20},
      ];
      const result = extractSDFT(data);
	expect(result).toEqual({
	    'a': {'histogram_bins': [2,3], 'histogram_log_bins':[]}})

    });
  });

  describe("extractPinnedRows", () => {
    it("should extract pinned rows correctly", () => {
      const data: DFData = [
        { index: "row1", value: 1 },
        { index: "row2", value: 2 },
        { index: "row3", value: 3 }
      ];
      const pinnedConfig: PinnedRowConfig[] = [
        { primary_key_val: "row1", displayer_args: { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 4 } },
        { primary_key_val: "row3", displayer_args: { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 4 } }
      ];
      const result = extractPinnedRows(data, pinnedConfig);
      expect(result).toEqual([
        { index: "row1", value: 1 },
        { index: "row3", value: 3 }
      ]);
    });

    it("should handle missing pinned rows", () => {
      const data: DFData = [
        { index: "row1", value: 1 }
      ];
      const pinnedConfig: PinnedRowConfig[] = [
        { primary_key_val: "row1", displayer_args: { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 4 } },
        { primary_key_val: "missing", displayer_args: { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 4 } }
      ];
      const result = extractPinnedRows(data, pinnedConfig);
      expect(result).toEqual([
        { index: "row1", value: 1 },
        undefined
      ]);
    });
  });

  describe("dfToAgrid", () => {
    it("should convert DFViewerConfig to AG Grid column definitions", () => {
      const config: DFViewerConfig = {
        column_config: [
          {
            col_name: "test",
            displayer_args: { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 4 }
          }
        ],
        pinned_rows: []
      };

      const result = dfToAgrid(config);
      expect(result).toHaveLength(1);
      expect(result[0].field).toBe("test");
      expect(result[0].headerName).toBe("test");
    });
  });

  describe("getHeightStyle", () => {
    it("should return correct height style for regular mode", () => {
      const config: DFViewerConfig = {
        column_config: [],
        pinned_rows: [],
        component_config: {
          height_fraction: 2
        }
      };
	const result = getHeightStyle2(100, config.pinned_rows.length, config.component_config);
      expect(result.classMode).toBe("regular-mode");
      expect(result.domLayout).toBe("normal");
    });

    it("should return correct height style for short mode", () => {
      const config: DFViewerConfig = {
        column_config: [],
        pinned_rows: [],
        component_config: {
          shortMode: true
        }
      };
      // Small number of rows
      const result = getHeightStyle2(5, config.pinned_rows.length, config.component_config);
      expect(result.classMode).toBe("short-mode");
      expect(result.domLayout).toBe("autoHeight");
    });
  });

  describe("getAutoSize", () => {
    it("should return fitProvidedWidth for 0 columns", () => {

      const result = getAutoSize(0);
      expect(result.type).toBe("fitProvidedWidth");
    });

    it("should return fitCellContents for positive columns", () => {
      const result = getAutoSize(5);
      expect(result.type).toBe("fitCellContents");
    });
  });

  describe("getGridOptions", () => {
    it("should create grid options with correct defaults", () => {
      // const setActiveCol = jest.fn();
      // const config: DFViewerConfig = {
      //   column_config: [],
      //   pinned_rows: []
      // };
      // const defaultColDef: ColDef = {};
      // const result = getGridOptions(
      //   "normal",
      //   { type: "fitCellContents" }
      // );
      //expect(result.rowSelection).toBe("single");
      //expect(result.enableCellTextSelection).toBe(true);
      //expect(result.tooltipShowDelay).toBe(0);
    });
  });
});

