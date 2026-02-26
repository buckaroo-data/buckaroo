//import { add, multiply } from "../src/math";

import { 
    extractSDFT,  
    extractPinnedRows,
    dfToAgrid,
    getHeightStyle2,
    getAutoSize,
    getSubChildren,
    childColDef,
    multiIndexColToColDef,

} from './gridUtils';
import * as _ from "lodash";
import { DFData, DFViewerConfig, NormalColumnConfig, MultiIndexColumnConfig, PinnedRowConfig, ColumnConfig } from "./DFWhole";
import { getFloatFormatter } from './Displayer';
import { ColDef, ValueFormatterParams } from '@ag-grid-community/core';

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
	    header_name: "test",
	    field:"test",
            displayer_args: { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 4 }
          }
        ],
        pinned_rows: [],
	left_col_configs: []
      };

      const result = dfToAgrid(config);
      expect(result).toHaveLength(1);
      expect((result[0] as ColDef).field).toBe("test");
      expect(result[0].headerName).toBe("test");
    });
  });

  describe("getHeightStyle", () => {
    it("should return correct height style for regular mode", () => {
      const config: DFViewerConfig = {
        column_config: [],
        pinned_rows: [],
	left_col_configs: [],
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
	left_col_configs: [],
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
      expect(result).toHaveProperty("defaultMinWidth", 80);
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



describe("testing multi index organiztion  ", () => {
  // mostly sanity checks to help develop gridUtils

  const [
    SUPER__SUB_A,
    SUPER__SUB_A2,
    SUPER__SUB_C,
    SUPER2__SUB_B]:MultiIndexColumnConfig[] = [
      {
	col_path:['super', 'sub_a'],
	'field': 'a',
	displayer_args: { displayer:'obj'}},
      { col_path:['super', 'sub_a2'],
	'field': 'a',
	displayer_args: { displayer:'obj'}},
      {col_path:['super', 'sub_c'],
	'field': 'c',
	displayer_args: { displayer:'obj'}},
      {
	col_path:['super2', 'b'],
	field:'b',
	displayer_args: { displayer:'obj'}},
    ];
  const REGULAR_C :NormalColumnConfig = {
    col_name:'c', 
    header_name: 'c',
    displayer_args: { displayer:'obj' }};

  const REGULAR_C__DIFFERENT_OBJECT :NormalColumnConfig = {
    col_name:'c', 
    header_name: 'c2',
    displayer_args: { displayer:'obj' }};

  const REGULAR_D :NormalColumnConfig = {
    col_name:'d', 
    header_name: 'd',
    displayer_args: { displayer:'obj' }};
  it("should group simple multi indexes properly", () => {
    const allMultiIndex: MultiIndexColumnConfig[] = [
      SUPER__SUB_A,
      SUPER__SUB_A2,
      SUPER__SUB_C,
      SUPER2__SUB_B];

    const grouped: MultiIndexColumnConfig[][] = [
      [SUPER__SUB_A,
	SUPER__SUB_A2,
	SUPER__SUB_C],
      [SUPER2__SUB_B]];
    
    expect(getSubChildren(allMultiIndex, 0)).toEqual(grouped);
  })

  it("should group mixed multi indexes properly", () => {
    const allMultiIndex: ColumnConfig[] = [
      SUPER__SUB_A,
      REGULAR_C,
      SUPER__SUB_A2,
      SUPER__SUB_C,
      SUPER2__SUB_B];

    const grouped:  ColumnConfig[][] = [
      [SUPER__SUB_A],
      [REGULAR_C],
      [SUPER__SUB_A2,
	SUPER__SUB_C],
      [SUPER2__SUB_B]];

    expect(getSubChildren(allMultiIndex, 0)).toEqual(grouped);
  });
  it("should group mixed multi indexes properly", () => {
    const allMultiIndex: ColumnConfig[] = [
      SUPER__SUB_A,
      REGULAR_C,
      SUPER__SUB_A2,
      SUPER__SUB_C,
      SUPER2__SUB_B];

    const grouped:  ColumnConfig[][] = [
      [SUPER__SUB_A],
      [REGULAR_C],
      [SUPER__SUB_A2,
	SUPER__SUB_C],
      [SUPER2__SUB_B]];

    expect(getSubChildren(allMultiIndex, 0)).toEqual(grouped);
  });
  it("should handle regular columns indexes properly", () => {
    const allMultiIndex: ColumnConfig[] = [
      REGULAR_C,
      REGULAR_D];
    const grouped:  ColumnConfig[][] = [
      [REGULAR_C],
      [REGULAR_D]];

    expect(getSubChildren(allMultiIndex, 0)).toEqual(grouped);
  });

  it("should handle repeated regular columns indexes properly", () => {
    const allMultiIndex: ColumnConfig[] = [
      REGULAR_C,
      REGULAR_C__DIFFERENT_OBJECT,
      REGULAR_D];
    const grouped:  ColumnConfig[][] = [
      [REGULAR_C],
      [REGULAR_C__DIFFERENT_OBJECT],
      [REGULAR_D]];

    expect(getSubChildren(allMultiIndex, 0)).toEqual(grouped);
  });


  it("childColDef should return proper subset", () => {
    expect(_.omit(childColDef(SUPER__SUB_A, 1), "valueFormatter")).toStrictEqual({
      "cellDataType": false,
      "cellStyle": undefined,
      "field": "a",
      "headerName": "sub_a",
    });

    expect(_.omit(childColDef(SUPER__SUB_A2, 1), "valueFormatter")).toStrictEqual({
      "cellDataType": false,
      "cellStyle": undefined,
      "field": "a",
      "headerName": "sub_a2",
    });

  });

  const [
    SUPER__SUB_FOO__SUB_B,
    SUPER__SUB_FOO__SUB_C,

    SUPER__SUB_BAR__SUB_B,
    SUPER__SUB_BAR__SUB_C,
  ]:MultiIndexColumnConfig[] = [
      {
	col_path:['super', 'sub_foo', 'sub_b'],
	'field': 'super__sub_foo__sub_b',
	displayer_args: { displayer:'obj'}},
      {
	col_path:['super', 'sub_foo', 'sub_c'],
	'field': 'super__sub_foo__sub_c',
	displayer_args: { displayer:'obj'}},


      {
	col_path:['super', 'sub_bar', 'sub_b'],
	'field': 'super__sub_bar__sub_b',
	displayer_args: { displayer:'obj'}},
      {
	col_path:['super', 'sub_bar', 'sub_c'],
	'field': 'super__sub_bar__sub_c',
	displayer_args: { displayer:'obj'}},
    ];


  it("multiIndexColumnConfig should return for 2 levels", () => {
    // first assume regular groups... Every element in a grouping will
    // have the same col_path depth.  I might want to break this later
    const groupedCC = [
      SUPER__SUB_A,
      SUPER__SUB_A2,
    ];

    const MIColGroupDef = multiIndexColToColDef(groupedCC);

    //@ts-ignore
    const children = MIColGroupDef.children;  
    expect(children.length).toBe(2);
    //@ts-ignore
    const child1 = children[0];
    //@ts-ignore
    expect(child1.children).toBe(undefined);  // there should only be one level of nesting
    const child2 = children[1];
    //@ts-ignore
    expect(child2.children).toBe(undefined);  // there should only be one level of nesting
  });


  it("multiIndexColumnConfig should return proper nested", () => {
    // first assume regular groups... Every element in a grouping will
    // have the same col_path depth.  I might want to break this later
    const groupedCC = [
      SUPER__SUB_FOO__SUB_B,
      SUPER__SUB_FOO__SUB_C,
      SUPER__SUB_BAR__SUB_B,
      SUPER__SUB_BAR__SUB_C
    ];

    const MIColGroupDef = multiIndexColToColDef(groupedCC);

    //@ts-ignore
    const children = MIColGroupDef.children;  
    expect(children.length).toBe(2);

    const child1 = children[0];
    //@ts-ignore
    const subChildren1 = child1.children;
    //@ts-ignore
    expect(child1.children.length).toBe(2)
  });

  it("multiIndexColumnConfig should return proper nested", () => {
    // make sure it doesn't break with singular items in col_path 

    const a: MultiIndexColumnConfig = {
      "col_path": [
        ""
      ],
      "field": "index_a",
      "displayer_args": {
        "displayer": "obj"
      }
    }
    const b: MultiIndexColumnConfig = {
      "col_path": [
        ""
      ],
      "field": "index_b",
      "displayer_args": {
        "displayer": "obj"
      }
    }
    console.log("a",a)
    const groupedCC: MultiIndexColumnConfig[] = [a,b];
    // console.log("groupedCC2", groupedCC2);
    // const groupedCC: MultiIndexColumnConfig[] = [
    // {
    //   "col_path": [
    //     ""
    //   ],
    //   "field": "index_a",
    //   "displayer_args": {
    //     "displayer": "obj"
    //   }
    // },

    // ]
    const MIColGroupDef = multiIndexColToColDef(groupedCC);

    //@ts-ignore
    const children = MIColGroupDef.children;  
    expect(children.length).toBe(2);

  });

  
});
