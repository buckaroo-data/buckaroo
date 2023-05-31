import { OperationDefaultArgs } from './OperationUtils';

export type TypeSpec = [number, string, 'type', 'integer' | 'float' | 'string'];
export type EnumSpec = [number, string, 'enum', string[]];
export type ColEnumSpec = [number, string, 'colEnum', string[]];

export type NoArgs = null;
export type ActualArg = TypeSpec | EnumSpec | ColEnumSpec;
export type ArgSpec = TypeSpec | EnumSpec | ColEnumSpec | NoArgs;

export interface SymbolT {
  symbol: string;
}

export interface SymbolDf {
  symbol: 'df';
}

export const symDf: SymbolDf = {
  symbol: 'df',
};

export type ColEnumArgs = Record<string, string>;

export type CommandArgSpec = Record<string, ArgSpec[]>;
export const bakedArgSpecs: CommandArgSpec = {
  dropcol: [null],
  fillna: [[3, 'fillVal', 'type', 'integer']],
  resample: [
    [3, 'frequency', 'enum', ['daily', 'weekly', 'monthly']],
    [4, 'colMap', 'colEnum', ['null', 'sum', 'mean', 'count']],
  ],
};

export type CommandConfigT = {
  argspecs: CommandArgSpec;
  defaultArgs: OperationDefaultArgs;
};
