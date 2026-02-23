import { IDatasource, IGetRowsParams } from "@ag-grid-community/core";
import { keys, times, reduce } from "lodash-es";

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

export const createRawDataWrapper = (data: any[]): RawDataWrapper => ({
  data,
  length: data.length,
  data_type: 'Raw'
});

export const createDatasourceWrapper = (data: DFData, delay_in_milliseconds: number = 0): DatasourceWrapper => {
  const tempDataSource: IDatasource = {
    rowCount: data.length,
    getRows(params: IGetRowsParams) {
      const slicedData = data.slice(params.startRow, params.endRow);
      if (delay_in_milliseconds > 0) {
        console.log("about to call setTimeout")
        setTimeout(() => {
          console.log("timeout finishing")
          params.successCallback(slicedData, data.length);
        }, delay_in_milliseconds);
      } else {
        params.successCallback(slicedData, data.length);
      }
    }
  };

  return {
    datasource: tempDataSource,
    data_type: "DataSource",
    length: data.length
  };
};

export const dictOfArraystoDFData = (dict: Record<string, any[]>): DFData => {
  const dictKeys = keys(dict);
  const length = dict[dictKeys[0]].length;

  return times(length, index => {
    return reduce(dictKeys, (result, key) => {
      result[key] = dict[key][index];
      return result;
    }, {} as Record<string, any>);
  });
};

export const arange = (N: number): number[] => {
  const retArr: number[] = [];
  for (let i = 0; i < N; i++) {
    retArr.push(i);
  }
  return retArr;
};

export const NRandom = (N: number, low: number, high: number): number[] => {
  const retArr: number[] = [];
  for (let i = 0; i < N; i++) {
    retArr.push(Math.floor((Math.random() * (high - low)) + low));
  }
  return retArr;
}; 

export const rd: RawDataWrapper = createRawDataWrapper([
    {'a':20, 'b':"foo"},
    {'a':30, 'b':"bar"}
]);
export const HistogramSummaryStats:DFData = [{
      'index': 'histogram',
      'a': [{ 'name': 'np.int64(35) - 39.0', 'tail': 1 },
      { 'name': '40-68', 'population': 29.0 },
      { 'name': '68-96', 'population': 16.0 },
      { 'name': '96-125', 'population': 14.0 },
      { 'name': '125-153', 'population': 11.0 },
      { 'name': '153-181', 'population': 10.0 },
      { 'name': '181-209', 'population': 8.0 },
      { 'name': '209-237', 'population': 5.0 },
      { 'name': '237-266', 'population': 3.0 },
      { 'name': '266-294', 'population': 2.0 },
      { 'name': '294-322', 'population': 2.0 },
      { 'name': '323.1500000000001 - np.int64(373)', 'tail': 1 }],
      'b': [{ 'name': 'np.int64(0) - 0.0', 'tail': 1 },
      { 'name': '2-4', 'population': 10.0 },
      { 'name': '4-6', 'population': 10.0 },
      { 'name': '6-7', 'population': 10.0 },
      { 'name': '7-9', 'population': 10.0 },
      { 'name': '9-11', 'population': 10.0 },
      { 'name': '11-13', 'population': 10.0 },
      { 'name': '13-15', 'population': 10.0 },
      { 'name': '15-16', 'population': 10.0 },
      { 'name': '16-18', 'population': 10.0 },
      { 'name': '18-20', 'population': 10.0 },
      { 'name': '21.0 - np.int64(21)', 'tail': 1 }],
      'c': [{ 'name': 'np.int64(1) - 1.0', 'tail': 1 },
      { 'name': '2-7', 'population': 11.0 },
      { 'name': '7-11', 'population': 11.0 },
      { 'name': '11-16', 'population': 9.0 },
      { 'name': '16-21', 'population': 7.0 },
      { 'name': '21-26', 'population': 11.0 },
      { 'name': '26-30', 'population': 11.0 },
      { 'name': '30-35', 'population': 9.0 },
      { 'name': '35-40', 'population': 11.0 },
      { 'name': '40-44', 'population': 10.0 },
      { 'name': '44-49', 'population': 11.0 },
      { 'name': '50.0 - np.int64(50)', 'tail': 1 }],
      'd': [{ 'name': 1, 'cat_pop': 38.0 },
      { 'name': 2, 'cat_pop': 21.0 },
      { 'name': 3, 'cat_pop': 21.0 },
      { 'name': 4, 'cat_pop': 20.0 }]
    },
    {
    index: 'histogram_bins',
    //hand entered for a, not completely accurate
    a: [ 2., 21.5, 41., 60.5, 80., 99.5, 119., 138.5, 158, 177.5, 197 ],
    b: [ 2, 4, 6, 7, 9, 11, 13, 15, 16, 18, 21],
    c: [ 2, 7, 11, 16, 21, 26, 30, 35, 40, 44, 50]
    }
  ]

    