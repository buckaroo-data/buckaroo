import { BuckarooState } from '../components/WidgetTypes';
import { IModel } from './IModel';
export type StatsModel = Pick<IModel, "get" | "on" | "off" | "send">;
export declare const DATAFLOW_STATE_FIELDS: readonly ["post_processing", "cleaning_method", "quick_command_args"];
export declare function touchesDataflow(_prev: BuckarooState | undefined, _next: BuckarooState | undefined): boolean;
export interface StatsRequestOptions {
    force?: boolean;
}
export declare function requestStats(_model: Pick<IModel, "get" | "send">, _opts?: StatsRequestOptions): boolean;
export interface OrchestratorOptions {
    model: StatsModel;
    minDebounceMs?: number;
    maxDebounceMs?: number;
    multiplier?: number;
    initialRequestMs?: number;
    firstPaintTimeoutMs?: number;
}
export declare class StateOrchestrator {
    constructor(_opts: OrchestratorOptions);
    start(): void;
    stop(): void;
    computeDebounce(): number;
}
