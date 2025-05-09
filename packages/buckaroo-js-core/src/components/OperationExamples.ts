// Centralized example operations for stories
import { sym } from "./OperationUtils";
import { symDf } from "./CommandUtils";
import { Operation, OperationDefaultArgs } from "./OperationUtils";
import { CommandArgSpec, CommandConfigT } from "./CommandUtils";

// Common sample operations
export const sampleOperations: Operation[] = [
  [sym("dropcol"), symDf, "col1"],
  [sym("fillna"), symDf, "col2", 5],
  [sym("resample"), symDf, "month", "monthly", {}],
];

export const manyOperations: Operation[] = [
  ...sampleOperations,
  [sym("dropcol"), symDf, "col3"],
  [sym("fillna"), symDf, "col4", 10],
  [sym("resample"), symDf, "year", "yearly", {}],
];

export const dataCleaningOps: Operation[] = [
  [{ symbol: "fillna", meta: { auto_clean: true, clean_strategy: "light-int" } }, symDf, "fruit-type", 5],
  [{ symbol: "remove_outliers", meta: { auto_clean: true, clean_strategy: "light-int" } }, symDf, "col1", 0.1],
  [{ symbol: "format_us_date", meta: { clean_strategy: "aggressive" } }, symDf, "probably_dates"],
  ...sampleOperations,
];

export const bakedOperationDefaults: OperationDefaultArgs = {
  dropcol: [sym("dropcol"), symDf, "col"],
  fillna: [sym("fillna"), symDf, "col", 8],
  remove_outliers: [sym("remove_outliers"), symDf, "col", 0.02],
  search: [sym("search"), symDf, "col", "term"],
  format_us_date: [sym("format_us_date"), symDf, "col"],
  resample: [sym("resample"), symDf, "col", "monthly", {}],
};

export const bakedArgSpecs: CommandArgSpec = {
  dropcol: [null],
  fillna: [[3, "fillVal", "type", "integer"]],
  remove_outliers: [[3, "tail", "type", "float"]],
  search: [[3, "needle", "type", "string"]],
  resample: [
    [3, "frequency", "enum", ["daily", "weekly", "monthly"]],
    [4, "colMap", "colEnum", ["null", "sum", "mean", "count"]],
  ],
};

export const bakedCommandConfig: CommandConfigT = {
  argspecs: bakedArgSpecs,
  defaultArgs: bakedOperationDefaults,
}; 