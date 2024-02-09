//import { add, multiply } from "../src/math";

import { extractSDFT,  getHistoIndex, } from '../../js/components/DFViewerParts/gridUtils';
import { DFData } from "../../js/components/DFViewerParts/DFWhole";
import { getFloatFormatter, getFormatter, objFormatter } from '../../js/components/DFViewerParts/Displayer';
import { ValueFormatterParams } from 'ag-grid-community';

describe("testing utility functions in gridUtils ", () => {
  // mostly sanity checks to help develop gridUtils

it("should test getFormater", () => {
//  expect(getFormatter({displayer: 'string'})).toBe(stringFormatter)
  expect(getFormatter({displayer: 'obj'})).toBe(objFormatter);


});

it("should format floats with a consistently spaced decimal pont",
  () => {
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

  }
)
  it("should convert to expected format", () => {
    const basicSDF:DFData = [
      {'index': 'histogram_bins',     'a':[2,3]},
      {'index': 'histogram_log_bins', 'a':[20,30], 'b': [10, 20]
    },
    ];
    const expected = {
      'a': {'histogram_bins': [2,3], 'histogram_log_bins': [20, 30]},
      'b': {'histogram_bins': [],    'histogram_log_bins': [10, 20]}
    };
    const result = extractSDFT(basicSDF);
    expect(result).toEqual(expected);
  });
  it("color mapper should pick from ranges properly", () => {
     /*
np.histogram([1, 2, 3, 4,  10, 20, 30, 40, 300, 300, 400, 500], bins=5)
( [  8,       0,     2,     1,     1], 
[  1. , 100.8, 200.6, 300.4, 400.2, 500. ])
The bottom matters for us, those are the endge

this means that 8 values are between 1 and 100.8  and 2 values are between 200.6 and 300.4
  */
  const edges = [2, 4, 10, 30];
  expect(getHistoIndex(1,  [])).toBe(0);
  expect(getHistoIndex(1,  edges)).toBe(0);
  expect(getHistoIndex(3,  edges)).toBe(1);
  expect(getHistoIndex(5,  edges)).toBe(2);
  expect(getHistoIndex(10, edges)).toBe(2);
  expect(getHistoIndex(11, edges)).toBe(3);
  expect(getHistoIndex(11000, edges)).toBe(4);

  });
});

