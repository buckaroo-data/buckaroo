import _ from 'lodash';
import { SymbolT, ColEnumArgs, SymbolDf, symDf } from './CommandUtils';

export const sym = (symbolName: string) => {
  return { symbol: symbolName };
};


export type Atom = number | string | SymbolT | ColEnumArgs;
export type SettableArg = number | string | ColEnumArgs;

export type OperationSingleColumn = [SymbolT, SymbolDf, string];
export type OperationSingleArg = [SymbolT, SymbolDf, string, Atom];
export type OperationTwoArg = [SymbolT, SymbolDf, string, Atom, Atom];
export type Operation =
  | OperationSingleColumn
  | OperationSingleArg
  | OperationTwoArg;

export type SetOperationFunc = (newCommand: Operation) => void;
export type SetOperationsFunc = (newCommands: Operation[]) => void;

export type OperationDefaultArgs = Record<string, Operation>;

//const ArgNames = ['Idx', 'label', 'specName', 'extraSpecArgs'];
export const bakedOperations: Operation[] = [
  [sym('dropcol'), symDf, 'col1'],
  [sym('fillna'), symDf, 'col2', 5],
  [sym('resample'), symDf, 'month', 'monthly', {}],
];

//this will become OperationEventFunc
export type OperationEventFunc = (newCommand: Operation) => void;
export type NoArgEventFunc = () => void;
