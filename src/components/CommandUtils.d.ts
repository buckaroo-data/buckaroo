import { OperationDefaultArgs } from './OperationUtils';
export type TypeSpec = [number, string, "type", "integer" | "float" | "string"];
export type EnumSpec = [number, string, "enum", string[]];
export type ColEnumSpec = [number, string, "colEnum", string[]];
export type NoArgs = null;
export type ActualArg = TypeSpec | EnumSpec | ColEnumSpec;
export type ArgSpec = TypeSpec | EnumSpec | ColEnumSpec | NoArgs;
export interface SymbolT {
    symbol: string;
    meta?: {
        auto_clean?: boolean;
        clean_strategy?: string;
    };
}
export interface SymbolDf {
    symbol: "df";
}
export declare const symDf: SymbolDf;
export type ColEnumArgs = Record<string, string>;
export type CommandArgSpec = Record<string, ArgSpec[]>;
export declare const bakedArgSpecs: CommandArgSpec;
export type CommandConfigT = {
    argspecs: CommandArgSpec;
    defaultArgs: OperationDefaultArgs;
};
